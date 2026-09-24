"""
utils/distance.py
-----------------
Haversine distance calculation between two geographic coordinates.

Assumptions:
- Earth radius = 6371 km (mean spherical radius, standard approximation).
- Coordinates are in decimal degrees (WGS-84 lat/lon).
- Returns distance in kilometres.
- No live GPS; coordinates come from data files only.
"""

import math


EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return the great-circle distance in kilometres between two points
    given as (lat1, lon1) and (lat2, lon2) in decimal degrees.

    Raises ValueError if any coordinate is outside valid ranges:
      latitude  : -90  .. 90
      longitude : -180 .. 180
    """
    for name, val, lo, hi in [
        ("lat1", lat1, -90, 90),
        ("lat2", lat2, -90, 90),
        ("lon1", lon1, -180, 180),
        ("lon2", lon2, -180, 180),
    ]:
        if not (lo <= val <= hi):
            raise ValueError(
                f"Invalid coordinate {name}={val!r}; must be in [{lo}, {hi}]"
            )

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
