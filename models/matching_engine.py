"""
models/matching_engine.py
==========================
Feature 4 — AI-Based NGO & Recipient Matching for BhojanSetu.

PURPOSE
-------
When a kitchen has confirmed surplus food, identify and rank suitable NGOs /
recipients.  This module implements a transparent, weighted scoring algorithm
(NOT machine-learned weights — the approach is honest algorithmic scoring).

INTEGRATION INTERFACE
---------------------
Key dataclasses
    SurplusRecord   – a confirmed surplus food item from a kitchen
    NGORecord       – a recipient/NGO with capacity and location
    NGOMatchResult  – one ranked candidate with full scoring breakdown

Key functions
    make_surplus_record(kitchen_id, food_item, quantity_kg,
                        date_of_surplus, expiry_time_hours, urgency,
                        surplus_id=None, status='confirmed') -> SurplusRecord

    load_ngo_records(ngo_list) -> list[NGORecord]
        Convert raw dicts (from load_ngos()) into NGORecord objects,
        skipping invalid/missing entries gracefully.

    match_ngos(surplus, ngo_records, kitchens=None,
               max_distance_km=50.0) -> list[NGOMatchResult]
        Filter, score and rank NGO candidates for a given surplus.
        Returns candidates sorted by score descending.

    format_ngo_match_report(surplus, matches) -> str
        Human-readable match report string.

Matching flow
    SurplusRecord
        ↓  filter: status='active', capacity>0, quantity compatible
        ↓  score: urgency + distance + capacity_fit + quantity_fit
        ↓  rank by composite score
        → list[NGOMatchResult]

Scoring weights (transparent algorithmic scoring)
    urgency      0.35   – critical=1.0, high=0.75, medium=0.50, low=0.25
    distance     0.25   – 1.0 at 0 km → 0.0 at max_distance_km; 0.5 if unknown
    capacity_fit 0.20   – 1.0 if NGO capacity >= surplus qty; partial credit
    quantity_fit 0.20   – 1.0 if NGO capacity can absorb full quantity

NGO record fields (from data/ngos.json)
    ngo_id, name, location, lat, lon, capacity_kg, status,
    food_preferences, contact

Surplus record fields (from data/surplus_log.csv)
    surplus_id, kitchen_id, food_item, quantity_kg, date_of_surplus,
    expiry_time_hours, urgency, status
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils.distance import haversine_km

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_DISTANCE_KM = 50.0

_URGENCY_SCORES: Dict[str, float] = {
    "critical": 1.00,
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
}

_WEIGHTS = {
    "urgency": 0.35,
    "distance": 0.25,
    "capacity_fit": 0.20,
    "quantity_fit": 0.20,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SurplusRecord:
    """Represents a confirmed surplus food item from a kitchen.

    Fields
    ------
    surplus_id          : str              – unique identifier (UUID4)
    kitchen_id          : str              – source kitchen
    food_item           : str              – food name
    quantity_kg         : float            – available surplus in kg (>0)
    date_of_surplus     : datetime.date    – date the surplus was recorded
    expiry_time_hours   : float            – hours until food expires (>0)
    urgency             : str              – low/medium/high/critical
    status              : str              – e.g. 'confirmed', 'matched'
    """

    surplus_id: str
    kitchen_id: str
    food_item: str
    quantity_kg: float
    date_of_surplus: datetime.date
    expiry_time_hours: float
    urgency: str
    status: str = "confirmed"

    def to_dict(self) -> dict:
        return {
            "surplus_id": self.surplus_id,
            "kitchen_id": self.kitchen_id,
            "food_item": self.food_item,
            "quantity_kg": self.quantity_kg,
            "date_of_surplus": self.date_of_surplus.isoformat(),
            "expiry_time_hours": self.expiry_time_hours,
            "urgency": self.urgency,
            "status": self.status,
        }


@dataclass
class NGORecord:
    """Represents one NGO / recipient.

    Fields
    ------
    ngo_id              : str          – unique identifier
    name                : str          – display name
    location            : str          – text description of location
    lat                 : float|None   – latitude (None if absent)
    lon                 : float|None   – longitude (None if absent)
    capacity_kg         : float        – maximum kg the NGO can accept
    status              : str          – 'active' or 'inactive'
    food_preferences    : list[str]    – e.g. ['cooked', 'raw']
    contact             : str          – contact info
    """

    ngo_id: str
    name: str
    location: str
    capacity_kg: float
    status: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    food_preferences: List[str] = field(default_factory=list)
    contact: str = ""

    def is_available(self) -> bool:
        """Return True only if status is 'active' and capacity > 0."""
        return self.status.strip().lower() == "active" and self.capacity_kg > 0


@dataclass
class NGOMatchResult:
    """One ranked NGO candidate.

    Fields
    ------
    ngo             : NGORecord    – the candidate
    score           : float        – composite score [0, 1]
    urgency_score   : float        – sub-score for urgency
    distance_score  : float        – sub-score for proximity
    capacity_score  : float        – sub-score for capacity fit
    quantity_score  : float        – sub-score for quantity fit
    distance_km     : float|None   – actual distance, or None if unknown
    reasons         : list[str]    – human-readable rationale
    """

    ngo: NGORecord
    score: float
    urgency_score: float
    distance_score: float
    capacity_score: float
    quantity_score: float
    distance_km: Optional[float]
    reasons: List[str]

    def to_dict(self) -> dict:
        return {
            "ngo_id": self.ngo.ngo_id,
            "name": self.ngo.name,
            "location": self.ngo.location,
            "distance_km": self.distance_km,
            "capacity_kg": self.ngo.capacity_kg,
            "score": self.score,
            "urgency_score": self.urgency_score,
            "distance_score": self.distance_score,
            "capacity_score": self.capacity_score,
            "quantity_score": self.quantity_score,
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# Factory / conversion helpers
# ---------------------------------------------------------------------------


def make_surplus_record(
    kitchen_id: str,
    food_item: str,
    quantity_kg,
    date_of_surplus: str,
    expiry_time_hours,
    urgency: str,
    surplus_id: Optional[str] = None,
    status: str = "confirmed",
) -> SurplusRecord:
    """Validate inputs and return a SurplusRecord.

    Parameters
    ----------
    kitchen_id          : str    – non-empty kitchen identifier
    food_item           : str    – non-empty food item name
    quantity_kg         : numeric – positive surplus quantity in kg
    date_of_surplus     : str    – date string (YYYY-MM-DD preferred)
    expiry_time_hours   : numeric – positive hours until expiry
    urgency             : str    – low/medium/high/critical
    surplus_id          : str | None – if None, a UUID4 is generated
    status              : str    – default 'confirmed'

    Returns
    -------
    SurplusRecord

    Raises
    ------
    ValueError for any invalid field.
    """
    from utils.validators import (
        validate_kitchen_id,
        validate_ingredient,
        validate_quantity,
        validate_date_str,
        validate_urgency,
    )

    kid = validate_kitchen_id(kitchen_id)
    fi = validate_ingredient(food_item)
    qty = validate_quantity(quantity_kg)

    try:
        exp = float(expiry_time_hours)
    except (TypeError, ValueError):
        raise ValueError(f"expiry_time_hours must be a number, got {expiry_time_hours!r}")
    if exp <= 0:
        raise ValueError(f"expiry_time_hours must be positive, got {exp}")

    dos = validate_date_str(date_of_surplus)
    urg = validate_urgency(urgency)
    sid = surplus_id.strip() if surplus_id else str(uuid.uuid4())
    if not sid:
        raise ValueError("surplus_id cannot be an empty string")

    return SurplusRecord(
        surplus_id=sid,
        kitchen_id=kid,
        food_item=fi,
        quantity_kg=qty,
        date_of_surplus=dos,
        expiry_time_hours=exp,
        urgency=urg,
        status=status,
    )


def load_ngo_records(ngo_list: List[dict]) -> List[NGORecord]:
    """Convert a list of raw NGO dicts into NGORecord objects.

    Invalid or incomplete records are silently skipped (logged to stderr).
    This is intentional: a single bad JSON record must not crash the system.

    Parameters
    ----------
    ngo_list : list[dict]  – typically the output of utils.data_loader.load_ngos()

    Returns
    -------
    list[NGORecord]
    """
    import sys

    records: List[NGORecord] = []
    for raw in ngo_list:
        try:
            ngo_id = str(raw.get("ngo_id", "")).strip()
            if not ngo_id:
                raise ValueError("missing ngo_id")
            name = str(raw.get("name", "")).strip() or ngo_id
            location = str(raw.get("location", "")).strip()
            status = str(raw.get("status", "inactive")).strip().lower()

            cap_raw = raw.get("capacity_kg", 0)
            try:
                capacity_kg = float(cap_raw)
            except (TypeError, ValueError):
                capacity_kg = 0.0

            lat = _safe_float(raw.get("lat"))
            lon = _safe_float(raw.get("lon"))
            food_prefs = raw.get("food_preferences", [])
            if not isinstance(food_prefs, list):
                food_prefs = []
            contact = str(raw.get("contact", "")).strip()

            records.append(
                NGORecord(
                    ngo_id=ngo_id,
                    name=name,
                    location=location,
                    capacity_kg=capacity_kg,
                    status=status,
                    lat=lat,
                    lon=lon,
                    food_preferences=food_prefs,
                    contact=contact,
                )
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[matching_engine] Skipping invalid NGO record {raw!r}: {exc}",
                file=sys.stderr,
            )
    return records


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _safe_float(value) -> Optional[float]:
    """Return float(value) or None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_score(distance_km: Optional[float], max_distance_km: float) -> float:
    """Score 1.0 at 0 km, linearly to 0.0 at max_distance_km; 0.5 if unknown."""
    if distance_km is None:
        return 0.5
    if distance_km <= 0:
        return 1.0
    if distance_km >= max_distance_km:
        return 0.0
    return 1.0 - (distance_km / max_distance_km)


def _capacity_score(capacity_kg: float, quantity_kg: float) -> float:
    """Score based on whether NGO capacity is sufficient.

    1.0 if capacity >= quantity
    partial (ratio) if capacity >= 50% of quantity
    0.0 if capacity < 50% of quantity
    """
    if capacity_kg >= quantity_kg:
        return 1.0
    ratio = capacity_kg / quantity_kg if quantity_kg > 0 else 0.0
    return ratio if ratio >= 0.5 else 0.0


def _quantity_fit_score(capacity_kg: float, quantity_kg: float) -> float:
    """Score based on how well the quantity fits within capacity.

    Perfect fit = not too small, not enormously over-capacity.
    1.0  if quantity == capacity
    0.8  if quantity < capacity (can absorb all, has extra capacity)
    partial for large mismatch
    """
    if capacity_kg <= 0:
        return 0.0
    if quantity_kg <= capacity_kg:
        return 1.0
    # quantity > capacity: score by how much it exceeds
    excess_ratio = quantity_kg / capacity_kg
    if excess_ratio <= 2.0:
        return 0.5  # can take half
    return 0.0


def _calc_distance(
    kitchen: Optional[dict], ngo: NGORecord
) -> Optional[float]:
    """Return Haversine distance in km if both have coordinates, else None."""
    if kitchen is None:
        return None
    k_lat = _safe_float(kitchen.get("lat"))
    k_lon = _safe_float(kitchen.get("lon"))
    if None in (k_lat, k_lon, ngo.lat, ngo.lon):
        return None
    try:
        return haversine_km(k_lat, k_lon, ngo.lat, ngo.lon)
    except (ValueError, TypeError):
        return None


def _build_reasons(
    urgency_score: float,
    dist_score: float,
    cap_score: float,
    qty_score: float,
    distance_km: Optional[float],
    quantity_kg: float,
    capacity_kg: float,
    ngo_name: str,
) -> List[str]:
    reasons: List[str] = []
    urg_label = {1.0: "critical", 0.75: "high", 0.5: "medium", 0.25: "low"}.get(
        urgency_score, f"score={urgency_score:.2f}"
    )
    reasons.append(f"Surplus urgency: {urg_label}")
    if distance_km is not None:
        reasons.append(f"Distance to {ngo_name}: {distance_km:.1f} km")
    else:
        reasons.append(f"Distance to {ngo_name}: unavailable (no coordinates)")
    if cap_score == 1.0:
        reasons.append(
            f"Capacity sufficient ({capacity_kg:.0f} kg capacity >= "
            f"{quantity_kg:.0f} kg surplus)"
        )
    elif cap_score > 0:
        reasons.append(
            f"Partial capacity ({capacity_kg:.0f} kg capacity for "
            f"{quantity_kg:.0f} kg surplus)"
        )
    else:
        reasons.append(
            f"Capacity insufficient ({capacity_kg:.0f} kg capacity < "
            f"50% of {quantity_kg:.0f} kg surplus)"
        )
    if qty_score == 1.0:
        reasons.append("Quantity fits within NGO capacity")
    elif qty_score > 0:
        reasons.append("Surplus slightly exceeds NGO capacity (partial)")
    else:
        reasons.append("Surplus greatly exceeds NGO capacity")
    return reasons


# ---------------------------------------------------------------------------
# Main matching function
# ---------------------------------------------------------------------------


def match_ngos(
    surplus: SurplusRecord,
    ngo_records: List[NGORecord],
    kitchens: Optional[Dict[str, dict]] = None,
    max_distance_km: float = _DEFAULT_MAX_DISTANCE_KM,
) -> List[NGOMatchResult]:
    """Filter and rank NGOs for a given surplus record.

    Parameters
    ----------
    surplus        : SurplusRecord        – the confirmed surplus
    ngo_records    : list[NGORecord]      – candidates (use load_ngo_records())
    kitchens       : dict[str,dict]|None  – kitchen records for distance calc
                                           (from utils.data_loader.load_kitchens())
    max_distance_km: float                – distance beyond which score=0

    Returns
    -------
    list[NGOMatchResult] sorted by composite score descending.

    Filtering rules (ALL must pass):
        1. NGO status must be 'active'
        2. NGO capacity must be > 0
        3. capacity_score must be > 0 (capacity >= 50% of surplus qty)

    Scoring weights:
        urgency      0.35
        distance     0.25
        capacity_fit 0.20
        quantity_fit 0.20
    """
    if kitchens is None:
        kitchens = {}

    kitchen = kitchens.get(surplus.kitchen_id)
    urg_sc = _URGENCY_SCORES.get(surplus.urgency, 0.5)
    results: List[NGOMatchResult] = []

    for ngo in ngo_records:
        # --- Filter ---
        if not ngo.is_available():
            continue
        cap_sc = _capacity_score(ngo.capacity_kg, surplus.quantity_kg)
        if cap_sc == 0.0:
            continue

        # --- Score ---
        dist_km = _calc_distance(kitchen, ngo)
        dist_sc = _distance_score(dist_km, max_distance_km)
        qty_sc = _quantity_fit_score(ngo.capacity_kg, surplus.quantity_kg)

        composite = (
            _WEIGHTS["urgency"] * urg_sc
            + _WEIGHTS["distance"] * dist_sc
            + _WEIGHTS["capacity_fit"] * cap_sc
            + _WEIGHTS["quantity_fit"] * qty_sc
        )

        reasons = _build_reasons(
            urgency_score=urg_sc,
            dist_score=dist_sc,
            cap_score=cap_sc,
            qty_score=qty_sc,
            distance_km=dist_km,
            quantity_kg=surplus.quantity_kg,
            capacity_kg=ngo.capacity_kg,
            ngo_name=ngo.name,
        )

        results.append(
            NGOMatchResult(
                ngo=ngo,
                score=round(composite, 4),
                urgency_score=urg_sc,
                distance_score=round(dist_sc, 4),
                capacity_score=round(cap_sc, 4),
                quantity_score=round(qty_sc, 4),
                distance_km=round(dist_km, 2) if dist_km is not None else None,
                reasons=reasons,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def format_ngo_match_report(surplus: SurplusRecord, matches: List[NGOMatchResult]) -> str:
    """Return a human-readable NGO match report string.

    Parameters
    ----------
    surplus : SurplusRecord
    matches : list[NGOMatchResult]

    Returns
    -------
    str – printable report
    """
    lines = [
        f"Food item   : {surplus.food_item}",
        f"Quantity    : {surplus.quantity_kg} kg",
        f"Kitchen ID  : {surplus.kitchen_id}",
        f"Urgency     : {surplus.urgency.capitalize()}",
        f"Expires in  : {surplus.expiry_time_hours} hours",
        "",
    ]
    if not matches:
        lines.append("No suitable NGO matches found.")
        return "\n".join(lines)

    for i, m in enumerate(matches, 1):
        dist_str = (
            f"{m.distance_km:.1f} km" if m.distance_km is not None else "unavailable"
        )
        lines += [
            f"--- Match #{i} ---",
            f"NGO         : {m.ngo.name} ({m.ngo.ngo_id})",
            f"Location    : {m.ngo.location}",
            f"Capacity    : {m.ngo.capacity_kg} kg",
            f"Distance    : {dist_str}",
            f"Score       : {m.score:.4f}",
            "Reasons:",
        ]
        for r in m.reasons:
            lines.append(f"  * {r}")
        lines.append("")
    return "\n".join(lines)
