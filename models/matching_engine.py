"""
models/matching_engine.py
--------------------------
Matches a food surplus entry to eligible NGO recipients.

Algorithm
---------
For each NGO candidate:
1. HARD FILTERS (eliminate if any fails):
   a. NGO must have lat/lon fields (otherwise skipped with a warning).
   b. NGO capacity_kg must be >= required quantity_kg (capacity check).
   c. If surplus is non-vegetarian, NGO food_preference must be "any".
      Vegetarian surplus is acceptable to all preferences.

2. SCORING (0–100, higher = better match):
   - Distance score  (40 pts): score = 40 * (1 - dist / MAX_DIST_KM)
     clamped to [0, 40].  MAX_DIST_KM = 50 km (configurable).
   - Urgency score   (40 pts): score = (urgency / 5) * 40
     urgency is an integer 1–5 provided by each NGO.
   - Capacity score  (20 pts): score = 20 * min(capacity_kg / quantity_kg, 1)
     Rewards NGOs that can take the full quantity.

3. Ranked list returned sorted by total score descending.

Assumptions
-----------
- quantity_kg must be > 0 to be a valid surplus.
- urgency is integer 1–5; missing urgency defaults to 1.
- capacity_kg missing defaults to 0 (NGO cannot receive anything).
- No fabricated match percentages; score reflects only the three factors above.
- Distance is straight-line (Haversine); road distance is not computed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from utils.distance import haversine

# Maximum considered distance in km; NGOs beyond this score 0 on distance.
MAX_DIST_KM: float = 50.0

# Weight breakdown (must sum to 100)
_W_DISTANCE = 40.0
_W_URGENCY = 40.0
_W_CAPACITY = 20.0

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_ngos(ngos_path: str | None = None) -> list[dict]:
    path = ngos_path or os.path.join(_DATA_DIR, "ngos.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_kitchens(kitchens_path: str | None = None) -> list[dict]:
    path = kitchens_path or os.path.join(_DATA_DIR, "kitchens.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def match_surplus(
    surplus: dict[str, Any],
    ngos: list[dict] | None = None,
    kitchens: list[dict] | None = None,
    max_dist_km: float = MAX_DIST_KM,
) -> dict[str, Any]:
    """
    Match a surplus record to eligible NGOs.

    Parameters
    ----------
    surplus : dict with keys:
        surplus_id  – str
        kitchen_id  – str
        food_name   – str
        quantity_kg – float  (must be > 0)
        food_type   – "vegetarian" | "non-vegetarian"
    ngos : list of NGO dicts (loaded from data/ngos.json if None)
    kitchens : list of kitchen dicts (loaded from data/kitchens.json if None)
    max_dist_km : distance cap for scoring

    Returns
    -------
    dict:
        surplus_id   – echoed back
        kitchen_id   – echoed back
        food_name    – echoed back
        quantity_kg  – echoed back
        matches      – list of match dicts sorted by score desc
        warnings     – list of non-fatal issues encountered
    """
    result: dict[str, Any] = {
        "surplus_id": surplus.get("surplus_id"),
        "kitchen_id": surplus.get("kitchen_id"),
        "food_name": surplus.get("food_name"),
        "quantity_kg": surplus.get("quantity_kg"),
        "matches": [],
        "warnings": [],
    }

    # --- Validate surplus ------------------------------------------------
    qty = surplus.get("quantity_kg", 0)
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        result["warnings"].append(
            f"quantity_kg={qty!r} is not numeric; cannot match."
        )
        return result

    if qty <= 0:
        result["warnings"].append(
            f"quantity_kg={qty} is not positive; no surplus to distribute."
        )
        return result

    food_type = str(surplus.get("food_type", "vegetarian")).lower()

    # --- Resolve kitchen coordinates ------------------------------------
    if ngos is None:
        ngos = _load_ngos()
    if kitchens is None:
        kitchens = _load_kitchens()

    kitchen_id = surplus.get("kitchen_id")
    kitchen = next((k for k in kitchens if k.get("id") == kitchen_id), None)
    if kitchen is None or "lat" not in kitchen or "lon" not in kitchen:
        result["warnings"].append(
            f"Kitchen '{kitchen_id}' not found or missing coordinates; "
            "distance scoring unavailable."
        )
        k_lat = k_lon = None
    else:
        k_lat = float(kitchen["lat"])
        k_lon = float(kitchen["lon"])

    # --- Score each NGO -------------------------------------------------
    matches: list[dict] = []
    for ngo in ngos:
        ngo_id = ngo.get("id", "?")

        # Hard filter: coordinates
        if "lat" not in ngo or "lon" not in ngo:
            result["warnings"].append(
                f"NGO '{ngo_id}' skipped: missing lat/lon coordinates."
            )
            continue

        try:
            n_lat = float(ngo["lat"])
            n_lon = float(ngo["lon"])
        except (TypeError, ValueError):
            result["warnings"].append(
                f"NGO '{ngo_id}' skipped: invalid coordinates."
            )
            continue

        # Hard filter: capacity
        capacity = float(ngo.get("capacity_kg", 0))
        if capacity < qty:
            result["warnings"].append(
                f"NGO '{ngo_id}' skipped: capacity {capacity} kg < "
                f"required {qty} kg."
            )
            continue

        # Hard filter: food preference
        preference = str(ngo.get("food_preference", "vegetarian")).lower()
        if food_type == "non-vegetarian" and preference != "any":
            result["warnings"].append(
                f"NGO '{ngo_id}' skipped: prefers vegetarian only, "
                "surplus is non-vegetarian."
            )
            continue

        # --- Distance score -------------------------------------------
        if k_lat is not None and k_lon is not None:
            try:
                dist_km = haversine(k_lat, k_lon, n_lat, n_lon)
            except ValueError as exc:
                result["warnings"].append(
                    f"NGO '{ngo_id}': distance calc failed – {exc}."
                )
                dist_km = max_dist_km  # penalise
        else:
            dist_km = max_dist_km  # unknown kitchen, assume worst

        dist_score = _W_DISTANCE * max(0.0, 1.0 - dist_km / max_dist_km)

        # --- Urgency score --------------------------------------------
        urgency = min(max(int(ngo.get("urgency", 1)), 1), 5)
        urgency_score = _W_URGENCY * (urgency / 5.0)

        # --- Capacity score -------------------------------------------
        cap_score = _W_CAPACITY * min(capacity / qty, 1.0)

        total_score = round(dist_score + urgency_score + cap_score, 2)

        matches.append(
            {
                "ngo_id": ngo_id,
                "ngo_name": ngo.get("name", ngo_id),
                "distance_km": round(dist_km, 3),
                "capacity_kg": capacity,
                "urgency": urgency,
                "score": total_score,
                "score_breakdown": {
                    "distance": round(dist_score, 2),
                    "urgency": round(urgency_score, 2),
                    "capacity": round(cap_score, 2),
                },
            }
        )

    matches.sort(key=lambda m: m["score"], reverse=True)
    result["matches"] = matches
    return result
