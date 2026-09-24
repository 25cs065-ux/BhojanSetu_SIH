"""
models/route_optimizer.py
--------------------------
Generates a delivery route from a kitchen (origin) through one or more
NGO stops (destinations).

Algorithm
---------
Nearest-Neighbour Greedy (NNG) heuristic:
  1. Start at the kitchen.
  2. Repeatedly visit the unvisited stop closest to the current position.
  3. Return total distance and ordered stop list.

NNG gives a good approximation for small delivery networks (< ~20 stops)
without the exponential cost of exact TSP.  For the typical BhojanSetu
scenario of 2–10 stops per delivery run this is entirely adequate.

Assumptions
-----------
- Distances are Haversine (straight-line); road distances are not computed.
- Coordinates must be present for both the kitchen and every NGO stop.
- Stops missing coordinates are excluded from the route with a warning.
- No live GPS tracking is performed.
- The route ends at the last NGO; there is no mandatory return to kitchen.
  (Return leg can be added by the caller if required.)
"""

from __future__ import annotations

import os
import json
from typing import Any

from utils.distance import haversine

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_kitchens(kitchens_path: str | None = None) -> list[dict]:
    path = kitchens_path or os.path.join(_DATA_DIR, "kitchens.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_ngos(ngos_path: str | None = None) -> list[dict]:
    path = ngos_path or os.path.join(_DATA_DIR, "ngos.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_coords(
    entity: dict, label: str, warnings: list[str]
) -> tuple[float, float] | None:
    """
    Extract and validate (lat, lon) from an entity dict.
    Returns None and appends a warning if missing or invalid.
    """
    if "lat" not in entity or "lon" not in entity:
        warnings.append(
            f"'{label}' is missing lat/lon; excluded from route."
        )
        return None
    try:
        lat = float(entity["lat"])
        lon = float(entity["lon"])
        # validate via haversine (reuses range check)
        haversine(lat, lon, lat, lon)
        return lat, lon
    except (ValueError, TypeError) as exc:
        warnings.append(
            f"'{label}' has invalid coordinates ({exc}); excluded from route."
        )
        return None


def build_route(
    kitchen_id: str,
    ngo_ids: list[str],
    kitchens: list[dict] | None = None,
    ngos: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Build a delivery route from kitchen_id through the given ngo_ids using
    the Nearest-Neighbour Greedy heuristic.

    Parameters
    ----------
    kitchen_id : ID of the origin kitchen
    ngo_ids    : list of NGO IDs to visit
    kitchens   : kitchen records (loaded from data/kitchens.json if None)
    ngos       : NGO records (loaded from data/ngos.json if None)

    Returns
    -------
    dict:
        kitchen_id       – echoed back
        ordered_stops    – list of stop dicts in delivery order:
            {stop_index, ngo_id, ngo_name, lat, lon,
             leg_distance_km, cumulative_distance_km}
        total_distance_km – total route distance (kitchen → last stop)
        excluded_stops   – list of ngo_ids that could not be routed
        warnings         – non-fatal messages
    """
    warnings: list[str] = []

    if kitchens is None:
        kitchens = _load_kitchens()
    if ngos is None:
        ngos = _load_ngos()

    # --- Resolve kitchen ------------------------------------------------
    kitchen = next((k for k in kitchens if k.get("id") == kitchen_id), None)
    if kitchen is None:
        warnings.append(f"Kitchen '{kitchen_id}' not found in data.")
        k_coords = None
    else:
        k_coords = _resolve_coords(kitchen, f"Kitchen:{kitchen_id}", warnings)

    # --- Resolve NGO coordinates ----------------------------------------
    ngo_lookup = {n["id"]: n for n in ngos if "id" in n}
    valid_stops: list[dict] = []
    excluded: list[str] = []

    for ngo_id in ngo_ids:
        ngo = ngo_lookup.get(ngo_id)
        if ngo is None:
            warnings.append(f"NGO '{ngo_id}' not found in data.")
            excluded.append(ngo_id)
            continue
        coords = _resolve_coords(ngo, f"NGO:{ngo_id}", warnings)
        if coords is None:
            excluded.append(ngo_id)
            continue
        valid_stops.append(
            {
                "ngo_id": ngo_id,
                "ngo_name": ngo.get("name", ngo_id),
                "lat": coords[0],
                "lon": coords[1],
            }
        )

    # --- Handle degenerate cases ----------------------------------------
    if not valid_stops:
        return {
            "kitchen_id": kitchen_id,
            "ordered_stops": [],
            "total_distance_km": 0.0,
            "excluded_stops": excluded,
            "warnings": warnings + ["No valid stops; route is empty."],
        }

    # --- Nearest-Neighbour Greedy heuristic ----------------------------
    if k_coords is None:
        # No kitchen origin; order by NGO list order, distance unknown
        warnings.append(
            "Kitchen coordinates unknown; stops ordered as supplied "
            "(no distance optimisation)."
        )
        ordered: list[dict] = []
        cum = 0.0
        for i, stop in enumerate(valid_stops):
            ordered.append(
                {
                    "stop_index": i + 1,
                    "ngo_id": stop["ngo_id"],
                    "ngo_name": stop["ngo_name"],
                    "lat": stop["lat"],
                    "lon": stop["lon"],
                    "leg_distance_km": None,
                    "cumulative_distance_km": None,
                }
            )
        return {
            "kitchen_id": kitchen_id,
            "ordered_stops": ordered,
            "total_distance_km": None,
            "excluded_stops": excluded,
            "warnings": warnings,
        }

    remaining = list(valid_stops)
    ordered = []
    cur_lat, cur_lon = k_coords
    cum_dist = 0.0

    while remaining:
        # Find nearest unvisited stop from current position
        nearest = min(
            remaining,
            key=lambda s: haversine(cur_lat, cur_lon, s["lat"], s["lon"]),
        )
        leg = round(haversine(cur_lat, cur_lon, nearest["lat"], nearest["lon"]), 3)
        cum_dist = round(cum_dist + leg, 3)
        ordered.append(
            {
                "stop_index": len(ordered) + 1,
                "ngo_id": nearest["ngo_id"],
                "ngo_name": nearest["ngo_name"],
                "lat": nearest["lat"],
                "lon": nearest["lon"],
                "leg_distance_km": leg,
                "cumulative_distance_km": cum_dist,
            }
        )
        cur_lat, cur_lon = nearest["lat"], nearest["lon"]
        remaining.remove(nearest)

    return {
        "kitchen_id": kitchen_id,
        "ordered_stops": ordered,
        "total_distance_km": cum_dist,
        "excluded_stops": excluded,
        "warnings": warnings,
    }
