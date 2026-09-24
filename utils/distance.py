"""
Haversine distance utility.

Provides a single public function:

    haversine_km(lat1, lon1, lat2, lon2) -> float
        Returns the great-circle distance in kilometres between two geographic
        coordinates given as decimal degrees.  Raises ValueError if any
        coordinate is outside the valid range.

If either kitchen lacks coordinate data the caller is responsible for
treating the result as "distance unavailable" rather than passing None here.
"""

import math

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two lat/lon points.

    Parameters
    ----------
    lat1, lon1 : float
        Decimal-degree coordinates of the first point.
    lat2, lon2 : float
        Decimal-degree coordinates of the second point.

    Returns
    -------
    float
        Distance in kilometres (>= 0.0).

    Raises
    ------
    ValueError
        If any latitude is outside [-90, 90] or any longitude outside
        [-180, 180].
    """
    for name, lat in (("lat1", lat1), ("lat2", lat2)):
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"{name} must be in [-90, 90]; got {lat}")
    for name, lon in (("lon1", lon1), ("lon2", lon2)):
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"{name} must be in [-180, 180]; got {lon}")

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c
