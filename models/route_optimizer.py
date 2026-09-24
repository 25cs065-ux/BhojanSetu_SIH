"""
models/route_optimizer.py
==========================
Feature 6 — Software-Based Pickup & Route Optimization for BhojanSetu.

PURPOSE
-------
After NGO matches are confirmed, calculate an efficient pickup/delivery
sequence from kitchen(s) to NGO destination(s).

This is SOFTWARE-BASED route optimization.  It does NOT require:
- live GPS tracking
- paid mapping APIs
- internet connectivity

It uses the coordinates already stored in the application data and the
existing Haversine distance utility.

ALGORITHM
---------
Nearest-Neighbour Greedy (NNG) with optional urgency pre-sorting:

1. If urgency data is present, critical/high-urgency stops are prepended
   to ensure they are visited first.
2. Starting from a given depot (kitchen), at each step the unvisited stop
   closest to the current position is appended to the route.
3. The algorithm is O(n²) which is perfectly acceptable for the expected
   number of stops (< 50 in a city-level system).

The result is not guaranteed to be globally optimal (that would require a
full TSP solver), but it produces a practical, deterministic route that
performs well for small to medium numbers of stops.

INTEGRATION INTERFACE
---------------------
Key dataclasses
    RouteStop    – one stop in the route (kitchen or NGO)
    OptimizedRoute – the full ordered route with distances

Key functions
    build_stops_from_matches(kitchen, ngo_matches) -> list[RouteStop]
        Convert a kitchen dict + list of NGOMatchResult/NutritionMatchResult
        into RouteStop objects ready for optimisation.

    optimize_route(stops, start_stop=None,
                   urgency_first=True) -> OptimizedRoute
        Run the nearest-neighbour algorithm and return an OptimizedRoute.

    format_route_report(route) -> str
        Human-readable route report.

RouteStop fields
    stop_id, name, lat, lon, stop_type ('kitchen'|'ngo'),
    urgency (optional), is_depot (True for starting kitchen)

OptimizedRoute fields
    stops           – ordered list[RouteStop]
    segment_km      – list[float] distance between consecutive stops
    cumulative_km   – list[float] cumulative distance at each stop
    total_km        – total route distance
    warnings        – list of any issues encountered (missing coords, etc.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from utils.distance import haversine_km

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_DEFAULT_URGENCY = "medium"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RouteStop:
    """One stop in the planned route.

    Fields
    ------
    stop_id    : str            – unique identifier (kitchen_id or ngo_id)
    name       : str            – human-readable display name
    lat        : float | None   – latitude (None = coordinates unavailable)
    lon        : float | None   – longitude (None = coordinates unavailable)
    stop_type  : str            – 'kitchen' | 'ngo' | 'unknown'
    urgency    : str            – low/medium/high/critical
    is_depot   : bool           – True for the starting kitchen
    """

    stop_id: str
    name: str
    lat: Optional[float]
    lon: Optional[float]
    stop_type: str = "unknown"
    urgency: str = _DEFAULT_URGENCY
    is_depot: bool = False

    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_dict(self) -> dict:
        return {
            "stop_id": self.stop_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "stop_type": self.stop_type,
            "urgency": self.urgency,
            "is_depot": self.is_depot,
        }


@dataclass
class OptimizedRoute:
    """The full optimised route.

    Fields
    ------
    stops           : list[RouteStop]   – ordered stops (depot first)
    segment_km      : list[float]       – distance between stop[i] and stop[i+1]
                                          None values where coords are missing
    cumulative_km   : list[float]       – cumulative distance at each stop
    total_km        : float             – total route length in km
    warnings        : list[str]         – non-fatal issues (missing coords, etc.)
    algorithm       : str               – algorithm used
    """

    stops: List[RouteStop]
    segment_km: List[Optional[float]]
    cumulative_km: List[float]
    total_km: float
    warnings: List[str] = field(default_factory=list)
    algorithm: str = "nearest-neighbour greedy"

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "total_km": round(self.total_km, 3),
            "stops": [
                {
                    **s.to_dict(),
                    "segment_km_to_next": self.segment_km[i]
                    if i < len(self.segment_km)
                    else None,
                    "cumulative_km": self.cumulative_km[i],
                }
                for i, s in enumerate(self.stops)
            ],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stop_from_kitchen(kitchen: dict) -> RouteStop:
    """Build a depot RouteStop from a kitchen dict."""
    return RouteStop(
        stop_id=str(kitchen.get("kitchen_id", "")).strip() or "depot",
        name=str(kitchen.get("name", "Kitchen")).strip(),
        lat=_safe_float(kitchen.get("lat")),
        lon=_safe_float(kitchen.get("lon")),
        stop_type="kitchen",
        urgency=_DEFAULT_URGENCY,
        is_depot=True,
    )


def _stop_from_ngo_match(match) -> RouteStop:
    """Build a RouteStop from an NGOMatchResult or NutritionMatchResult.

    Handles both types:
    - NGOMatchResult  → match.ngo
    - NutritionMatchResult → match.base_match.ngo
    """
    # Support both NGOMatchResult and NutritionMatchResult
    ngo = getattr(match, "ngo", None)
    if ngo is None:
        base = getattr(match, "base_match", None)
        if base is not None:
            ngo = getattr(base, "ngo", None)
    if ngo is None:
        raise ValueError(f"Cannot extract NGO from match object: {match!r}")

    # Extract urgency from surplus context if available (via match attributes)
    urgency = _DEFAULT_URGENCY  # default

    return RouteStop(
        stop_id=str(ngo.ngo_id).strip(),
        name=str(ngo.name).strip(),
        lat=ngo.lat,
        lon=ngo.lon,
        stop_type="ngo",
        urgency=urgency,
        is_depot=False,
    )


def build_stops_from_matches(
    kitchen: dict,
    ngo_matches: list,
    surplus_urgency: str = _DEFAULT_URGENCY,
) -> List[RouteStop]:
    """Build RouteStop list from a kitchen dict and a list of NGO matches.

    Parameters
    ----------
    kitchen          : dict  – kitchen record (must have kitchen_id, name, lat, lon)
    ngo_matches      : list  – list of NGOMatchResult or NutritionMatchResult objects
    surplus_urgency  : str   – urgency level of the surplus (used for all NGO stops)

    Returns
    -------
    list[RouteStop]  – depot kitchen first, then NGO stops.
    Empty list if ngo_matches is empty (but depot is still included).
    """
    depot = _stop_from_kitchen(kitchen)
    stops: List[RouteStop] = [depot]
    for match in ngo_matches:
        stop = _stop_from_ngo_match(match)
        stop.urgency = str(surplus_urgency).strip().lower() or _DEFAULT_URGENCY
        stops.append(stop)
    return stops


def build_stops_from_dicts(stop_dicts: List[dict]) -> List[RouteStop]:
    """Build RouteStop list from plain dicts (for direct/flexible use).

    Each dict may have: stop_id, name, lat, lon, stop_type, urgency, is_depot.
    Missing fields fall back to defaults.

    Parameters
    ----------
    stop_dicts : list[dict]

    Returns
    -------
    list[RouteStop]
    """
    stops: List[RouteStop] = []
    for d in stop_dicts:
        stops.append(
            RouteStop(
                stop_id=str(d.get("stop_id", "")).strip() or "unknown",
                name=str(d.get("name", "")).strip() or "Unknown",
                lat=_safe_float(d.get("lat")),
                lon=_safe_float(d.get("lon")),
                stop_type=str(d.get("stop_type", "unknown")).strip(),
                urgency=str(d.get("urgency", _DEFAULT_URGENCY)).strip().lower(),
                is_depot=bool(d.get("is_depot", False)),
            )
        )
    return stops


# ---------------------------------------------------------------------------
# Distance helper
# ---------------------------------------------------------------------------


def _distance_between(a: RouteStop, b: RouteStop) -> Optional[float]:
    """Return Haversine distance in km between two stops, or None."""
    if not a.has_coordinates() or not b.has_coordinates():
        return None
    try:
        return haversine_km(a.lat, a.lon, b.lat, b.lon)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Nearest-neighbour greedy route algorithm
# ---------------------------------------------------------------------------


def optimize_route(
    stops: List[RouteStop],
    start_stop: Optional[RouteStop] = None,
    urgency_first: bool = True,
) -> OptimizedRoute:
    """Compute an optimised pickup/delivery route using nearest-neighbour greedy.

    Parameters
    ----------
    stops         : list[RouteStop]     – all stops including depot
    start_stop    : RouteStop | None    – starting position; if None, the first
                                         stop marked is_depot=True is used,
                                         or stops[0] if no depot is marked.
    urgency_first : bool                – if True, critical/high-urgency stops
                                          are visited before nearest-neighbour
                                          ordering kicks in for the rest.

    Returns
    -------
    OptimizedRoute with ordered stops, segment distances, and cumulative km.

    Notes
    -----
    - Stops without coordinates are appended at the end of the route and a
      warning is recorded (no distance fabricated).
    - Duplicate stop_ids are kept (user's responsibility to de-duplicate).
    - A single stop (depot only) returns a trivial route with zero distance.
    """
    warnings: List[str] = []

    if not stops:
        return OptimizedRoute(
            stops=[],
            segment_km=[],
            cumulative_km=[],
            total_km=0.0,
            warnings=["No stops provided."],
        )

    # Determine the starting stop
    if start_stop is None:
        depot_candidates = [s for s in stops if s.is_depot]
        start_stop = depot_candidates[0] if depot_candidates else stops[0]

    # Separate stops with and without coordinates
    with_coords = [s for s in stops if s.has_coordinates() and s is not start_stop]
    without_coords = [s for s in stops if not s.has_coordinates() and s is not start_stop]

    if without_coords:
        for s in without_coords:
            warnings.append(
                f"Stop '{s.name}' ({s.stop_id}) has no coordinates — "
                "appended at end of route, distance not calculated."
            )

    # Optionally pre-sort urgent stops
    if urgency_first:
        urgent = [
            s for s in with_coords
            if s.urgency in ("critical", "high")
        ]
        non_urgent = [
            s for s in with_coords
            if s.urgency not in ("critical", "high")
        ]
        # Sort urgent stops by urgency level then by distance from depot
        urgent.sort(
            key=lambda s: (
                _URGENCY_ORDER.get(s.urgency, 99),
                _distance_between(start_stop, s) or math.inf,
            )
        )
        # Non-urgent will be ordered by nearest-neighbour below
        with_coords_ordered_urgent = urgent
        remaining_pool = non_urgent
    else:
        with_coords_ordered_urgent = []
        remaining_pool = list(with_coords)

    # Build the route using nearest-neighbour for the remaining pool
    ordered: List[RouteStop] = [start_stop]

    # First, append urgent stops in urgency-priority order
    current = start_stop
    for urgent_stop in with_coords_ordered_urgent:
        ordered.append(urgent_stop)
        current = urgent_stop

    # Then, greedily pick the nearest unvisited stop
    unvisited = list(remaining_pool)
    while unvisited:
        best_stop = None
        best_dist = math.inf
        for candidate in unvisited:
            d = _distance_between(current, candidate)
            if d is None:
                d = math.inf
            if d < best_dist:
                best_dist = d
                best_stop = candidate
        if best_stop is None:
            # All remaining stops have no coords relative to current
            ordered.extend(unvisited)
            break
        ordered.append(best_stop)
        unvisited.remove(best_stop)
        current = best_stop

    # Append stops without coordinates at the end
    ordered.extend(without_coords)

    # Compute segment and cumulative distances
    segment_km: List[Optional[float]] = []
    cumulative_km: List[float] = [0.0]
    running = 0.0

    for i in range(len(ordered) - 1):
        d = _distance_between(ordered[i], ordered[i + 1])
        segment_km.append(d)
        if d is not None:
            running += d
        cumulative_km.append(round(running, 3))

    return OptimizedRoute(
        stops=ordered,
        segment_km=segment_km,
        cumulative_km=cumulative_km,
        total_km=round(running, 3),
        warnings=warnings,
        algorithm="nearest-neighbour greedy"
        + (" with urgency pre-sort" if urgency_first else ""),
    )


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------


def format_route_report(route: OptimizedRoute) -> str:
    """Return a human-readable route report string.

    Parameters
    ----------
    route : OptimizedRoute

    Returns
    -------
    str – printable multi-line report
    """
    lines = [
        f"Algorithm      : {route.algorithm}",
        f"Total distance : {route.total_km:.2f} km",
        f"Stops          : {len(route.stops)}",
        "",
    ]

    if not route.stops:
        lines.append("No stops in route.")
        return "\n".join(lines)

    for i, stop in enumerate(route.stops):
        prefix = "DEPOT ->" if stop.is_depot else f"Stop {i:>2} ->" if i < len(route.stops) - 1 else f"Stop {i:>2}  "
        coord_str = (
            f"({stop.lat:.4f}, {stop.lon:.4f})"
            if stop.has_coordinates()
            else "(no coordinates)"
        )
        seg = ""
        if i < len(route.segment_km):
            d = route.segment_km[i]
            seg = f"  [next: {d:.2f} km]" if d is not None else "  [next: ??? km]"
        lines.append(
            f"{prefix} [{stop.stop_type.upper()}] {stop.name} "
            f"{coord_str}  cumulative={route.cumulative_km[i]:.2f} km{seg}"
        )

    if route.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in route.warnings:
            lines.append(f"  ! {w}")

    return "\n".join(lines)
