"""
models/raw_material_exchange.py
================================
Pre-Production Raw Material Exchange module for BhojanSetu.

PURPOSE
-------
Allow institutional kitchens to record excess raw ingredients BEFORE they are
cooked and match those ingredients with other kitchens that need them.

This is NOT cooked-food / NGO redistribution.

INTEGRATION INTERFACE
---------------------
Key classes
    RawMaterialListing   – represents one kitchen's excess supply
    KitchenNeed          – represents one kitchen's requirement
    MatchResult          – a ranked candidate with scoring breakdown
    ExchangeProposal     – tracks the lifecycle of a proposed exchange

Key functions
    create_listing(kitchen_id, ingredient, quantity, unit,
                   date_listed, use_by_date=None) -> RawMaterialListing

    create_need(kitchen_id, ingredient, required_quantity,
                required_date, urgency='medium') -> KitchenNeed

    find_matches(need, listings, kitchens=None) -> list[MatchResult]
        Returns candidates ranked best-first.  Pass the kitchens dict
        (from load_kitchens()) to enable distance scoring.

    propose_exchange(listing, need, offered_quantity) -> ExchangeProposal

    transition_exchange(proposal, new_status) -> ExchangeProposal
        Raises ValueError for invalid transitions.

Exchange status lifecycle
    AVAILABLE → MATCH_FOUND → PROPOSAL_CREATED → ACCEPTED → COMPLETED
                                               ↘ DECLINED → CANCELLED
    Any terminal state (COMPLETED / CANCELLED) cannot be re-transitioned.

Ranking factors (all normalised to [0, 1], higher = better match)
    1. urgency_score      – critical=1.0, high=0.75, medium=0.5, low=0.25
    2. use_by_score       – 1.0 if use_by_date within 3 days; decays linearly
                            to 0 over 30 days; 0.5 if no use_by_date
    3. quantity_score     – 1.0 if available >= required; partial credit if
                            available covers ≥50 % of required quantity
    4. distance_score     – 1.0 at 0 km, decays to 0 at MAX_DISTANCE_KM (50);
                            0.5 if coordinates unavailable

Weights: urgency 0.35, use_by 0.25, quantity 0.25, distance 0.15
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils.validators import (
    validate_date_str,
    validate_ingredient,
    validate_kitchen_id,
    validate_quantity,
    validate_unit,
    validate_urgency,
    validate_use_by_date,
)
from utils.distance import haversine_km

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DISTANCE_KM = 50.0  # beyond this distance_score = 0

_URGENCY_SCORES: Dict[str, float] = {
    "critical": 1.00,
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
}

_WEIGHTS = {
    "urgency": 0.35,
    "use_by": 0.25,
    "quantity": 0.25,
    "distance": 0.15,
}

# Allowed status transition graph
# key = current status, value = set of valid next statuses
_STATUS_TRANSITIONS: Dict[str, set] = {
    "AVAILABLE": {"MATCH_FOUND"},
    "MATCH_FOUND": {"PROPOSAL_CREATED", "AVAILABLE"},
    "PROPOSAL_CREATED": {"ACCEPTED", "DECLINED"},
    "ACCEPTED": {"COMPLETED"},
    "DECLINED": {"CANCELLED"},
    "COMPLETED": set(),   # terminal
    "CANCELLED": set(),   # terminal
}

_LISTING_STATUSES = frozenset(_STATUS_TRANSITIONS.keys())


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RawMaterialListing:
    """Represents a kitchen's available excess raw ingredient.

    Fields
    ------
    listing_id      : str              – auto-generated UUID4
    kitchen_id      : str              – owning kitchen
    ingredient      : str              – ingredient name (normalised)
    quantity        : float            – available quantity (> 0)
    unit            : str              – canonical lower-cased unit
    date_listed     : datetime.date    – date this listing was created
    use_by_date     : date | None      – expiry date if known
    status          : str              – one of _LISTING_STATUSES
    """

    kitchen_id: str
    ingredient: str
    quantity: float
    unit: str
    date_listed: datetime.date
    use_by_date: Optional[datetime.date] = None
    status: str = "AVAILABLE"
    listing_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "kitchen_id": self.kitchen_id,
            "ingredient": self.ingredient,
            "quantity": self.quantity,
            "unit": self.unit,
            "date_listed": self.date_listed.isoformat(),
            "use_by_date": self.use_by_date.isoformat() if self.use_by_date else "",
            "status": self.status,
        }


@dataclass
class KitchenNeed:
    """Represents a kitchen's requirement for a raw ingredient.

    Fields
    ------
    kitchen_id        : str              – requesting kitchen
    ingredient        : str              – ingredient needed (normalised)
    required_quantity : float            – quantity needed (> 0)
    required_date     : datetime.date    – date by which it is needed
    urgency           : str              – low / medium / high / critical
    """

    kitchen_id: str
    ingredient: str
    required_quantity: float
    required_date: datetime.date
    urgency: str = "medium"


@dataclass
class MatchResult:
    """A ranked match candidate returned by find_matches().

    Fields
    ------
    listing         : RawMaterialListing  – the candidate listing
    score           : float               – composite score [0, 1]
    urgency_score   : float               – sub-score for urgency
    use_by_score    : float               – sub-score for use-by proximity
    quantity_score  : float               – sub-score for quantity fit
    distance_score  : float               – sub-score for proximity
    distance_km     : float | None        – actual distance in km, or None
    reasons         : list[str]           – human-readable match rationale
    """

    listing: RawMaterialListing
    score: float
    urgency_score: float
    use_by_score: float
    quantity_score: float
    distance_score: float
    distance_km: Optional[float]
    reasons: List[str]


@dataclass
class ExchangeProposal:
    """Tracks the lifecycle of a proposed raw-material exchange.

    Fields
    ------
    exchange_id           : str           – auto-generated UUID4
    listing_id            : str           – linked listing
    offering_kitchen_id   : str           – kitchen supplying the ingredient
    requesting_kitchen_id : str           – kitchen requesting it
    ingredient            : str
    offered_quantity      : float         – quantity in this proposal
    requested_quantity    : float         – quantity the requester needs
    unit                  : str
    status                : str           – exchange lifecycle status
    created_at            : datetime      – creation timestamp
    updated_at            : datetime      – last-update timestamp
    """

    listing_id: str
    offering_kitchen_id: str
    requesting_kitchen_id: str
    ingredient: str
    offered_quantity: float
    requested_quantity: float
    unit: str
    status: str = "PROPOSAL_CREATED"
    exchange_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "exchange_id": self.exchange_id,
            "listing_id": self.listing_id,
            "offering_kitchen_id": self.offering_kitchen_id,
            "requesting_kitchen_id": self.requesting_kitchen_id,
            "ingredient": self.ingredient,
            "offered_quantity": self.offered_quantity,
            "requested_quantity": self.requested_quantity,
            "unit": self.unit,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------


def create_listing(
    kitchen_id: str,
    ingredient: str,
    quantity,
    unit: str,
    date_listed: str,
    use_by_date: Optional[str] = None,
) -> RawMaterialListing:
    """Validate inputs and return a RawMaterialListing.

    Parameters
    ----------
    kitchen_id   : str   – non-empty kitchen identifier
    ingredient   : str   – non-empty ingredient name
    quantity     : numeric – positive available quantity
    unit         : str   – must be in VALID_UNITS (utils/validators.py)
    date_listed  : str   – parseable date string (YYYY-MM-DD preferred)
    use_by_date  : str | None – optional parseable date string

    Returns
    -------
    RawMaterialListing with status='AVAILABLE'

    Raises
    ------
    ValueError for any invalid field.
    """
    return RawMaterialListing(
        kitchen_id=validate_kitchen_id(kitchen_id),
        ingredient=validate_ingredient(ingredient),
        quantity=validate_quantity(quantity),
        unit=validate_unit(unit),
        date_listed=validate_date_str(date_listed),
        use_by_date=validate_use_by_date(use_by_date),
        status="AVAILABLE",
    )


def create_need(
    kitchen_id: str,
    ingredient: str,
    required_quantity,
    required_date: str,
    urgency: str = "medium",
) -> KitchenNeed:
    """Validate inputs and return a KitchenNeed.

    Parameters
    ----------
    kitchen_id        : str     – non-empty kitchen identifier
    ingredient        : str     – non-empty ingredient name
    required_quantity : numeric – positive required quantity
    required_date     : str     – parseable date string
    urgency           : str     – low / medium / high / critical (default medium)

    Returns
    -------
    KitchenNeed

    Raises
    ------
    ValueError for any invalid field.
    """
    return KitchenNeed(
        kitchen_id=validate_kitchen_id(kitchen_id),
        ingredient=validate_ingredient(ingredient),
        required_quantity=validate_quantity(required_quantity),
        required_date=validate_date_str(required_date),
        urgency=validate_urgency(urgency),
    )


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------


def _ingredients_compatible(a: str, b: str) -> bool:
    """Return True if two ingredient names refer to the same item.

    Comparison is case-insensitive and ignores leading/trailing whitespace.
    """
    return a.strip().lower() == b.strip().lower()


def _use_by_score(use_by_date: Optional[datetime.date], today: datetime.date) -> float:
    """Score based on urgency of use-by date.

    - No use_by_date           → 0.5  (neutral; cannot assess)
    - ≤ 3 days until expiry    → 1.0  (most urgent)
    - 3–30 days                → linear decay from 1.0 to 0.0
    - > 30 days                → 0.0
    """
    if use_by_date is None:
        return 0.5
    days_left = (use_by_date - today).days
    if days_left <= 3:
        return 1.0
    if days_left <= 30:
        return 1.0 - (days_left - 3) / 27.0
    return 0.0


def _quantity_score(available: float, required: float) -> float:
    """Score based on how well available quantity meets the requirement.

    - available >= required → 1.0  (perfect or surplus)
    - available >= 50 % of required → linear from 0.5 to 1.0
    - available < 50 % of required → 0.0  (not enough to be useful)
    """
    if available >= required:
        return 1.0
    ratio = available / required
    if ratio >= 0.5:
        return ratio  # 0.5 ≤ score < 1.0
    return 0.0


def _distance_score(distance_km: Optional[float]) -> float:
    """Score based on distance between kitchens.

    - No coordinates            → 0.5  (neutral; cannot assess)
    - 0 km                      → 1.0
    - MAX_DISTANCE_KM           → 0.0
    - Beyond MAX_DISTANCE_KM    → 0.0
    """
    if distance_km is None:
        return 0.5
    if distance_km <= 0:
        return 1.0
    if distance_km >= MAX_DISTANCE_KM:
        return 0.0
    return 1.0 - (distance_km / MAX_DISTANCE_KM)


def _calculate_distance(
    offering_kitchen: dict, requesting_kitchen: dict
) -> Optional[float]:
    """Return Haversine distance in km if both kitchens have coordinates.

    Returns None and does NOT fabricate a distance if coordinates are missing.
    """
    lat1 = offering_kitchen.get("lat")
    lon1 = offering_kitchen.get("lon")
    lat2 = requesting_kitchen.get("lat")
    lon2 = requesting_kitchen.get("lon")
    if None in (lat1, lon1, lat2, lon2):
        return None
    try:
        return haversine_km(float(lat1), float(lon1), float(lat2), float(lon2))
    except (ValueError, TypeError):
        return None


def _build_reasons(
    ingredient_match: bool,
    qty_score: float,
    use_by_sc: float,
    dist_sc: float,
    distance_km: Optional[float],
    urgency_sc: float,
    available: float,
    required: float,
    unit: str,
) -> List[str]:
    reasons: List[str] = []
    if ingredient_match:
        reasons.append("Ingredient compatible")
    if qty_score == 1.0:
        reasons.append(
            f"Quantity sufficient ({available:.2g} {unit} available vs "
            f"{required:.2g} {unit} required)"
        )
    elif qty_score > 0:
        reasons.append(
            f"Partial quantity ({available:.2g} {unit} available, "
            f"{required:.2g} {unit} required)"
        )
    if use_by_sc >= 0.8:
        reasons.append("Use-by date is imminent – high disposal urgency")
    elif use_by_sc >= 0.5:
        reasons.append("Use-by date is approaching")
    elif use_by_sc == 0.5:
        reasons.append("No use-by date specified")
    if distance_km is not None:
        reasons.append(f"Distance: {distance_km:.1f} km")
    else:
        reasons.append("Distance: unavailable (no coordinates)")
    urgency_label = {1.0: "critical", 0.75: "high", 0.5: "medium", 0.25: "low"}.get(
        urgency_sc, f"score={urgency_sc:.2f}"
    )
    reasons.append(f"Requirement urgency: {urgency_label}")
    return reasons


def find_matches(
    need: KitchenNeed,
    listings: List[RawMaterialListing],
    kitchens: Optional[Dict[str, dict]] = None,
) -> List[MatchResult]:
    """Find and rank listings that can satisfy a KitchenNeed.

    Parameters
    ----------
    need      : KitchenNeed           – the requesting kitchen's requirement
    listings  : list[RawMaterialListing] – candidate listings to search
    kitchens  : dict[str, dict] | None   – kitchen records keyed by kitchen_id
                                          (load with utils.data_loader.load_kitchens)
                                          Pass None to disable distance scoring.

    Returns
    -------
    list[MatchResult] sorted by composite score descending (best match first).
    An empty list is returned when no compatible listing is found.

    Filtering rules (must ALL pass):
        1. Ingredient must be compatible (case-insensitive).
        2. Listing kitchen must differ from requesting kitchen.
        3. Listing status must be 'AVAILABLE'.
        4. Quantity score must be > 0 (available >= 50 % of required).

    Ranking factors (weighted sum):
        urgency  0.35  – need urgency
        use_by   0.25  – how soon the listing expires
        quantity 0.25  – how well available qty fits required qty
        distance 0.15  – geographic proximity (0.5 if unknown)
    """
    if kitchens is None:
        kitchens = {}

    today = datetime.date.today()
    requesting_kitchen = kitchens.get(need.kitchen_id, {})
    results: List[MatchResult] = []

    for listing in listings:
        # --- Filter step ---
        if not _ingredients_compatible(listing.ingredient, need.ingredient):
            continue
        if listing.kitchen_id == need.kitchen_id:
            continue
        if listing.status != "AVAILABLE":
            continue

        qty_sc = _quantity_score(listing.quantity, need.required_quantity)
        if qty_sc == 0.0:
            continue  # not enough to be useful

        # --- Score step ---
        urg_sc = _URGENCY_SCORES.get(need.urgency, 0.5)
        ub_sc = _use_by_score(listing.use_by_date, today)

        offering_kitchen = kitchens.get(listing.kitchen_id, {})
        if requesting_kitchen and offering_kitchen:
            dist_km = _calculate_distance(offering_kitchen, requesting_kitchen)
        else:
            dist_km = None
        dist_sc = _distance_score(dist_km)

        composite = (
            _WEIGHTS["urgency"] * urg_sc
            + _WEIGHTS["use_by"] * ub_sc
            + _WEIGHTS["quantity"] * qty_sc
            + _WEIGHTS["distance"] * dist_sc
        )

        reasons = _build_reasons(
            ingredient_match=True,
            qty_score=qty_sc,
            use_by_sc=ub_sc,
            dist_sc=dist_sc,
            distance_km=dist_km,
            urgency_sc=urg_sc,
            available=listing.quantity,
            required=need.required_quantity,
            unit=listing.unit,
        )

        results.append(
            MatchResult(
                listing=listing,
                score=round(composite, 4),
                urgency_score=urg_sc,
                use_by_score=round(ub_sc, 4),
                quantity_score=round(qty_sc, 4),
                distance_score=round(dist_sc, 4),
                distance_km=round(dist_km, 2) if dist_km is not None else None,
                reasons=reasons,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def format_match_report(need: KitchenNeed, matches: List[MatchResult]) -> str:
    """Return a human-readable match report string.

    Parameters
    ----------
    need    : KitchenNeed
    matches : list[MatchResult]  – output of find_matches()

    Returns
    -------
    str  – printable report
    """
    lines = [
        f"Ingredient: {need.ingredient}",
        f"Required: {need.required_quantity} (by {need.required_date})",
        f"Urgency: {need.urgency.capitalize()}",
        f"Requesting kitchen: {need.kitchen_id}",
        "",
    ]
    if not matches:
        lines.append("No compatible listings found.")
        return "\n".join(lines)

    for i, m in enumerate(matches, 1):
        dist_str = (
            f"{m.distance_km:.1f} km" if m.distance_km is not None else "unavailable"
        )
        lines += [
            f"--- Match #{i} ---",
            f"Kitchen ID  : {m.listing.kitchen_id}",
            f"Available   : {m.listing.quantity} {m.listing.unit}",
            f"Use-by date : {m.listing.use_by_date or 'not specified'}",
            f"Distance    : {dist_str}",
            f"Score       : {m.score:.4f}",
            "Match reasons:",
        ]
        for r in m.reasons:
            lines.append(f"  * {r}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exchange lifecycle
# ---------------------------------------------------------------------------


def propose_exchange(
    listing: RawMaterialListing,
    need: KitchenNeed,
    offered_quantity: float,
) -> ExchangeProposal:
    """Create an ExchangeProposal for an accepted match.

    Parameters
    ----------
    listing          : RawMaterialListing  – the matching listing
    need             : KitchenNeed         – the requesting kitchen's need
    offered_quantity : float               – quantity agreed to transfer
                                            (must be > 0)

    Returns
    -------
    ExchangeProposal with status='PROPOSAL_CREATED'

    Raises
    ------
    ValueError  if listing is not AVAILABLE or offered_quantity is invalid.
    """
    if listing.status != "AVAILABLE":
        raise ValueError(
            f"Cannot propose exchange: listing {listing.listing_id!r} has "
            f"status {listing.status!r} (must be 'AVAILABLE')."
        )
    oq = validate_quantity(offered_quantity)
    if oq > listing.quantity:
        raise ValueError(
            f"offered_quantity ({oq}) exceeds listing quantity ({listing.quantity})."
        )
    return ExchangeProposal(
        listing_id=listing.listing_id,
        offering_kitchen_id=listing.kitchen_id,
        requesting_kitchen_id=need.kitchen_id,
        ingredient=listing.ingredient,
        offered_quantity=oq,
        requested_quantity=need.required_quantity,
        unit=listing.unit,
        status="PROPOSAL_CREATED",
    )


def transition_exchange(proposal: ExchangeProposal, new_status: str) -> ExchangeProposal:
    """Move a proposal to a new status, validating the transition.

    Valid transitions
    -----------------
    PROPOSAL_CREATED → ACCEPTED
    PROPOSAL_CREATED → DECLINED
    ACCEPTED         → COMPLETED
    DECLINED         → CANCELLED
    COMPLETED        → (terminal – no further transitions)
    CANCELLED        → (terminal – no further transitions)

    Parameters
    ----------
    proposal   : ExchangeProposal
    new_status : str  – target status (case-insensitive)

    Returns
    -------
    The same ExchangeProposal object with status and updated_at mutated.

    Raises
    ------
    ValueError  if the transition is not allowed.
    """
    target = new_status.strip().upper()
    allowed = _STATUS_TRANSITIONS.get(proposal.status, set())

    if not allowed:
        raise ValueError(
            f"Exchange {proposal.exchange_id!r} is in terminal state "
            f"{proposal.status!r} and cannot be transitioned."
        )
    if target not in allowed:
        raise ValueError(
            f"Invalid status transition: {proposal.status!r} → {target!r}. "
            f"Allowed next states: {sorted(allowed)}"
        )
    proposal.status = target
    proposal.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return proposal
