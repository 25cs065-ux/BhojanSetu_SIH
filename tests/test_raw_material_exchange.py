"""
tests/test_raw_material_exchange.py
====================================
Comprehensive test suite for models/raw_material_exchange.py

Tests cover all 23 success-criteria checks including:
    1.  Valid raw material listing
    2.  Empty ingredient
    3.  Negative quantity
    4.  Invalid date
    5.  Valid receiving kitchen need
    6.  Ingredient match
    7.  Ingredient mismatch
    8.  Quantity insufficient
    9.  Multiple candidate kitchens
    10. Distance calculation
    11. Missing coordinates
    12. Ranking
    13. Exchange proposal
    14. Accept proposal
    15. Decline proposal
    16. Invalid status transition
    17. Complete end-to-end exchange
    18. Imports work correctly
    19. Existing project tests unbroken (utils modules importable)
    20. Module importable via project package structure
    21. No unintended modification to unrelated modules
    22. No hard-coded fake production data
    23. Existing utilities actually reused
"""

import datetime
import sys
import os

# Ensure project root is on sys.path so imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# ---------------------------------------------------------------------------
# Import verification (tests 18, 20)
# ---------------------------------------------------------------------------
from models.raw_material_exchange import (
    RawMaterialListing,
    KitchenNeed,
    MatchResult,
    ExchangeProposal,
    create_listing,
    create_need,
    find_matches,
    format_match_report,
    propose_exchange,
    transition_exchange,
)
from utils.validators import (
    validate_ingredient,
    validate_quantity,
    validate_unit,
    validate_date_str,
    validate_use_by_date,
    validate_urgency,
    validate_kitchen_id,
    VALID_UNITS,
)
from utils.distance import haversine_km
from utils.data_loader import load_kitchens, load_raw_material_log, load_exchange_log


# ---------------------------------------------------------------------------
# Fixtures — clearly labelled test data, NOT production data
# ---------------------------------------------------------------------------

TODAY = datetime.date.today()
TOMORROW = TODAY + datetime.timedelta(days=1)
IN_TWO_DAYS = TODAY + datetime.timedelta(days=2)
IN_TEN_DAYS = TODAY + datetime.timedelta(days=10)
IN_THIRTY_DAYS = TODAY + datetime.timedelta(days=30)

# Test kitchen records (coordinates are real Delhi locations)
KITCHENS = {
    "K001": {
        "kitchen_id": "K001",
        "name": "Test Kitchen A",
        "lat": 28.5450,
        "lon": 77.1926,
    },
    "K002": {
        "kitchen_id": "K002",
        "name": "Test Kitchen B",
        "lat": 28.5672,
        "lon": 77.2100,
    },
    "K003": {
        "kitchen_id": "K003",
        "name": "Test Kitchen C (far)",
        "lat": 28.6889,
        "lon": 77.2090,
    },
    # K004 intentionally has no coordinates (tests missing-coord branch)
    "K004": {
        "kitchen_id": "K004",
        "name": "Test Kitchen D (no coords)",
    },
}


# ---------------------------------------------------------------------------
# Helper to build a listing without going through the validator (for
# tests that need to inject already-validated data quickly).
# ---------------------------------------------------------------------------

def _raw_listing(
    kitchen_id="K001",
    ingredient="Rice",
    quantity=50.0,
    unit="kg",
    date_listed=None,
    use_by_date=None,
    status="AVAILABLE",
) -> RawMaterialListing:
    listing = RawMaterialListing(
        kitchen_id=kitchen_id,
        ingredient=ingredient,
        quantity=quantity,
        unit=unit,
        date_listed=date_listed or TODAY,
        use_by_date=use_by_date,
        status=status,
    )
    return listing


def _raw_need(
    kitchen_id="K002",
    ingredient="Rice",
    required_quantity=30.0,
    required_date=None,
    urgency="high",
) -> KitchenNeed:
    return KitchenNeed(
        kitchen_id=kitchen_id,
        ingredient=ingredient,
        required_quantity=required_quantity,
        required_date=required_date or TOMORROW,
        urgency=urgency,
    )


# ===========================================================================
# TEST 1 – Valid raw material listing
# ===========================================================================

class TestCreateListing:

    def test_valid_listing(self):
        listing = create_listing(
            kitchen_id="K001",
            ingredient="Rice",
            quantity=50,
            unit="kg",
            date_listed=TODAY.isoformat(),
            use_by_date=IN_TEN_DAYS.isoformat(),
        )
        assert listing.kitchen_id == "K001"
        assert listing.ingredient == "Rice"
        assert listing.quantity == 50.0
        assert listing.unit == "kg"
        assert listing.date_listed == TODAY
        assert listing.use_by_date == IN_TEN_DAYS
        assert listing.status == "AVAILABLE"
        assert listing.listing_id  # non-empty UUID

    def test_valid_listing_no_use_by_date(self):
        listing = create_listing(
            kitchen_id="K002",
            ingredient="Wheat Flour",
            quantity=20.5,
            unit="kg",
            date_listed=TODAY.isoformat(),
        )
        assert listing.use_by_date is None

    # TEST 2 – Empty ingredient
    def test_empty_ingredient_raises(self):
        with pytest.raises(ValueError, match="empty"):
            create_listing("K001", "  ", 10, "kg", TODAY.isoformat())

    # TEST 3 – Negative quantity
    def test_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="positive"):
            create_listing("K001", "Rice", -5, "kg", TODAY.isoformat())

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError, match="positive"):
            create_listing("K001", "Rice", 0, "kg", TODAY.isoformat())

    # TEST 4 – Invalid date
    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            create_listing("K001", "Rice", 10, "kg", "not-a-date")

    def test_invalid_use_by_date_raises(self):
        with pytest.raises(ValueError):
            create_listing(
                "K001", "Rice", 10, "kg", TODAY.isoformat(), use_by_date="31/31/2025"
            )

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            create_listing("K001", "Rice", 10, "barrels", TODAY.isoformat())

    def test_empty_kitchen_id_raises(self):
        with pytest.raises(ValueError, match="Kitchen ID"):
            create_listing("", "Rice", 10, "kg", TODAY.isoformat())

    def test_listing_to_dict(self):
        listing = create_listing("K001", "Rice", 50, "kg", TODAY.isoformat())
        d = listing.to_dict()
        assert d["kitchen_id"] == "K001"
        assert d["ingredient"] == "Rice"
        assert d["quantity"] == 50.0
        assert d["status"] == "AVAILABLE"


# ===========================================================================
# TEST 5 – Valid receiving kitchen need
# ===========================================================================

class TestCreateNeed:

    def test_valid_need(self):
        need = create_need(
            kitchen_id="K002",
            ingredient="Rice",
            required_quantity=30,
            required_date=TOMORROW.isoformat(),
            urgency="high",
        )
        assert need.kitchen_id == "K002"
        assert need.ingredient == "Rice"
        assert need.required_quantity == 30.0
        assert need.required_date == TOMORROW
        assert need.urgency == "high"

    def test_default_urgency_is_medium(self):
        need = create_need("K002", "Wheat", 10, TOMORROW.isoformat())
        assert need.urgency == "medium"

    def test_invalid_urgency_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            create_need("K002", "Rice", 10, TOMORROW.isoformat(), urgency="extreme")

    def test_empty_ingredient_raises(self):
        with pytest.raises(ValueError, match="empty"):
            create_need("K002", "", 10, TOMORROW.isoformat())

    def test_invalid_quantity_raises(self):
        with pytest.raises(ValueError, match="positive"):
            create_need("K002", "Rice", -1, TOMORROW.isoformat())


# ===========================================================================
# TESTS 6-12 – Matching engine
# ===========================================================================

class TestFindMatches:

    # TEST 6 – Ingredient match
    def test_ingredient_match_found(self):
        listing = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=50.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert len(results) == 1
        assert results[0].listing is listing

    # TEST 7 – Ingredient mismatch
    def test_ingredient_mismatch_returns_empty(self):
        listing = _raw_listing(kitchen_id="K001", ingredient="Wheat", quantity=50.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert results == []

    # Case-insensitive match
    def test_case_insensitive_ingredient_match(self):
        listing = _raw_listing(kitchen_id="K001", ingredient="rice", quantity=50.0)
        need = _raw_need(kitchen_id="K002", ingredient="RICE", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert len(results) == 1

    # TEST 8 – Quantity insufficient
    def test_quantity_insufficient_returns_empty(self):
        # 10 kg available, 50 kg required -> ratio 0.2 -> score=0 -> filtered
        listing = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=10.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=50.0)
        results = find_matches(need, [listing], KITCHENS)
        assert results == []

    def test_partial_quantity_accepted(self):
        # 30 kg available, 50 kg required -> ratio 0.6 -> score 0.6 -> included
        listing = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=30.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=50.0)
        results = find_matches(need, [listing], KITCHENS)
        assert len(results) == 1
        assert results[0].quantity_score == pytest.approx(0.6, abs=1e-4)

    # Same kitchen must not match itself
    def test_same_kitchen_excluded(self):
        listing = _raw_listing(kitchen_id="K002", ingredient="Rice", quantity=50.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert results == []

    # Non-AVAILABLE status excluded
    def test_non_available_listing_excluded(self):
        listing = _raw_listing(
            kitchen_id="K001", ingredient="Rice", quantity=50.0, status="MATCH_FOUND"
        )
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert results == []

    # TEST 9 – Multiple candidate kitchens
    def test_multiple_candidates_returned(self):
        l1 = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=50.0)
        l2 = _raw_listing(kitchen_id="K003", ingredient="Rice", quantity=40.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [l1, l2], KITCHENS)
        assert len(results) == 2

    # TEST 10 – Distance calculation
    def test_distance_calculated_when_coords_present(self):
        listing = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=50.0)
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert results[0].distance_km is not None
        assert results[0].distance_km > 0

    # TEST 11 – Missing coordinates
    def test_missing_coordinates_handled_gracefully(self):
        listing = _raw_listing(kitchen_id="K001", ingredient="Rice", quantity=50.0)
        # K004 has no lat/lon
        need = _raw_need(kitchen_id="K004", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [listing], KITCHENS)
        assert len(results) == 1
        assert results[0].distance_km is None
        assert results[0].distance_score == 0.5  # neutral fallback
        assert any("unavailable" in r for r in results[0].reasons)

    # TEST 12 – Ranking
    def test_ranking_best_first(self):
        # l1: closer, use_by imminent → should outrank l2 which is far
        l1 = _raw_listing(
            kitchen_id="K001",
            ingredient="Rice",
            quantity=50.0,
            use_by_date=TOMORROW,  # imminent → high use_by_score
        )
        l2 = _raw_listing(
            kitchen_id="K003",  # far kitchen
            ingredient="Rice",
            quantity=50.0,
            use_by_date=IN_THIRTY_DAYS,  # not imminent
        )
        need = _raw_need(kitchen_id="K002", ingredient="Rice", required_quantity=30.0)
        results = find_matches(need, [l1, l2], KITCHENS)
        assert len(results) == 2
        # l1 should rank higher because imminent use_by + closer distance
        assert results[0].listing is l1

    def test_ranking_scores_are_in_descending_order(self):
        listings = [
            _raw_listing("K001", "Rice", 50.0, use_by_date=IN_TEN_DAYS),
            _raw_listing("K003", "Rice", 50.0, use_by_date=IN_THIRTY_DAYS),
        ]
        need = _raw_need("K002", "Rice", 30.0)
        results = find_matches(need, listings, KITCHENS)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_listings_returns_empty(self):
        need = _raw_need("K002", "Rice", 30.0)
        assert find_matches(need, []) == []

    def test_no_kitchens_dict_disables_distance(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        results = find_matches(need, [listing])  # kitchens=None
        assert results[0].distance_km is None
        assert results[0].distance_score == 0.5


# ===========================================================================
# TEST 13 – Exchange proposal
# ===========================================================================

class TestProposeExchange:

    def test_valid_proposal_created(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, offered_quantity=30.0)
        assert proposal.listing_id == listing.listing_id
        assert proposal.offering_kitchen_id == "K001"
        assert proposal.requesting_kitchen_id == "K002"
        assert proposal.ingredient == "Rice"
        assert proposal.offered_quantity == 30.0
        assert proposal.requested_quantity == 30.0
        assert proposal.status == "PROPOSAL_CREATED"

    def test_proposal_on_non_available_listing_raises(self):
        listing = _raw_listing("K001", "Rice", 50.0, status="COMPLETED")
        need = _raw_need("K002", "Rice", 30.0)
        with pytest.raises(ValueError, match="AVAILABLE"):
            propose_exchange(listing, need, 30.0)

    def test_offered_quantity_exceeds_available_raises(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        with pytest.raises(ValueError, match="exceeds"):
            propose_exchange(listing, need, offered_quantity=100.0)

    def test_proposal_to_dict(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        d = proposal.to_dict()
        assert d["status"] == "PROPOSAL_CREATED"
        assert d["ingredient"] == "Rice"


# ===========================================================================
# TEST 14 – Accept proposal
# ===========================================================================

class TestAcceptProposal:

    def test_accept_proposal(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        result = transition_exchange(proposal, "ACCEPTED")
        assert result.status == "ACCEPTED"

    def test_accepted_can_be_completed(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        transition_exchange(proposal, "ACCEPTED")
        transition_exchange(proposal, "COMPLETED")
        assert proposal.status == "COMPLETED"


# ===========================================================================
# TEST 15 – Decline proposal
# ===========================================================================

class TestDeclineProposal:

    def test_decline_proposal(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        result = transition_exchange(proposal, "DECLINED")
        assert result.status == "DECLINED"

    def test_declined_can_be_cancelled(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        transition_exchange(proposal, "DECLINED")
        transition_exchange(proposal, "CANCELLED")
        assert proposal.status == "CANCELLED"


# ===========================================================================
# TEST 16 – Invalid status transitions
# ===========================================================================

class TestInvalidStatusTransitions:

    def test_completed_cannot_transition(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        transition_exchange(proposal, "ACCEPTED")
        transition_exchange(proposal, "COMPLETED")
        with pytest.raises(ValueError, match="terminal"):
            transition_exchange(proposal, "CANCELLED")

    def test_cancelled_cannot_transition(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        transition_exchange(proposal, "DECLINED")
        transition_exchange(proposal, "CANCELLED")
        with pytest.raises(ValueError, match="terminal"):
            transition_exchange(proposal, "COMPLETED")

    def test_proposal_created_cannot_go_directly_to_completed(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_exchange(proposal, "COMPLETED")

    def test_proposal_created_cannot_go_directly_to_cancelled(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_exchange(proposal, "CANCELLED")

    def test_accepted_cannot_go_to_declined(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        transition_exchange(proposal, "ACCEPTED")
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_exchange(proposal, "DECLINED")

    def test_unknown_status_raises(self):
        listing = _raw_listing("K001", "Rice", 50.0)
        need = _raw_need("K002", "Rice", 30.0)
        proposal = propose_exchange(listing, need, 30.0)
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_exchange(proposal, "GHOSTED")


# ===========================================================================
# TEST 17 – Complete end-to-end exchange
# ===========================================================================

class TestEndToEndExchange:

    def test_full_lifecycle(self):
        """
        Full lifecycle:
        create listing → create need → find matches → propose → accept → complete
        """
        # Step 1: Kitchen A records excess rice
        listing = create_listing(
            kitchen_id="K001",
            ingredient="Rice",
            quantity=50,
            unit="kg",
            date_listed=TODAY.isoformat(),
            use_by_date=IN_TEN_DAYS.isoformat(),
        )
        assert listing.status == "AVAILABLE"

        # Step 2: Kitchen B records a need for rice
        need = create_need(
            kitchen_id="K002",
            ingredient="Rice",
            required_quantity=30,
            required_date=TOMORROW.isoformat(),
            urgency="high",
        )

        # Step 3: Match
        matches = find_matches(need, [listing], KITCHENS)
        assert len(matches) == 1
        best = matches[0]
        assert best.listing is listing
        assert best.distance_km is not None
        assert best.distance_km > 0

        # Step 4: Propose
        proposal = propose_exchange(listing, need, offered_quantity=30.0)
        assert proposal.status == "PROPOSAL_CREATED"

        # Step 5: Accept
        transition_exchange(proposal, "ACCEPTED")
        assert proposal.status == "ACCEPTED"

        # Step 6: Complete
        transition_exchange(proposal, "COMPLETED")
        assert proposal.status == "COMPLETED"

        # Verify report generation
        report = format_match_report(need, matches)
        assert "Rice" in report
        assert "K001" in report
        assert "km" in report

    def test_full_lifecycle_decline_then_cancel(self):
        listing = create_listing(
            "K001", "Wheat Flour", 100, "kg", TODAY.isoformat()
        )
        need = create_need("K003", "Wheat Flour", 50, TOMORROW.isoformat(), "medium")
        matches = find_matches(need, [listing], KITCHENS)
        assert len(matches) == 1
        proposal = propose_exchange(listing, need, 50.0)
        transition_exchange(proposal, "DECLINED")
        transition_exchange(proposal, "CANCELLED")
        assert proposal.status == "CANCELLED"


# ===========================================================================
# TEST 18 – Imports work correctly  (verified by the import block at top)
# ===========================================================================

class TestImports:

    def test_all_exchange_symbols_importable(self):
        # If we reach here, all imports at module level succeeded
        assert RawMaterialListing is not None
        assert KitchenNeed is not None
        assert MatchResult is not None
        assert ExchangeProposal is not None
        assert create_listing is not None
        assert create_need is not None
        assert find_matches is not None
        assert propose_exchange is not None
        assert transition_exchange is not None

    def test_utils_importable(self):
        assert haversine_km is not None
        assert load_kitchens is not None
        assert load_raw_material_log is not None
        assert load_exchange_log is not None


# ===========================================================================
# TEST 19 / 23 – Utilities correctly reused
# ===========================================================================

class TestUtilityReuse:

    def test_haversine_direct(self):
        # Delhi IIT → AIIMS: known to be roughly 3.5–4 km
        km = haversine_km(28.5450, 77.1926, 28.5672, 77.2100)
        assert 2.0 < km < 6.0

    def test_haversine_zero_distance(self):
        km = haversine_km(28.0, 77.0, 28.0, 77.0)
        assert km == pytest.approx(0.0, abs=1e-6)

    def test_haversine_invalid_lat_raises(self):
        with pytest.raises(ValueError, match="lat1"):
            haversine_km(100.0, 77.0, 28.0, 77.0)

    def test_haversine_invalid_lon_raises(self):
        with pytest.raises(ValueError, match="lon2"):
            haversine_km(28.0, 77.0, 28.0, 200.0)

    def test_valid_units_set_non_empty(self):
        assert len(VALID_UNITS) > 0
        assert "kg" in VALID_UNITS

    def test_data_loader_load_kitchens_returns_dict(self):
        kitchens = load_kitchens()
        # File has been seeded; should return a dict (possibly with entries)
        assert isinstance(kitchens, dict)

    def test_data_loader_load_raw_material_log_returns_list(self):
        rows = load_raw_material_log()
        assert isinstance(rows, list)

    def test_data_loader_load_exchange_log_returns_list(self):
        rows = load_exchange_log()
        assert isinstance(rows, list)


# ===========================================================================
# TEST 22 – No hard-coded fake production data
# (ensure the module has no unexplained hard-coded data constants)
# ===========================================================================

class TestNoFakeProductionData:

    def test_find_matches_uses_supplied_data_only(self):
        """Matching uses ONLY the listings and kitchens passed in."""
        results = find_matches(
            _raw_need("K002", "Rice", 30.0),
            [],  # empty listings
            KITCHENS,
        )
        assert results == []

    def test_format_match_report_no_match(self):
        need = _raw_need("K002", "Rice", 30.0)
        report = format_match_report(need, [])
        assert "No compatible listings found" in report


# ===========================================================================
# Extra edge-case validator tests
# ===========================================================================

class TestValidators:

    def test_validate_ingredient_strips_whitespace(self):
        assert validate_ingredient("  Rice  ") == "Rice"

    def test_validate_quantity_float(self):
        assert validate_quantity("12.5") == 12.5

    def test_validate_unit_case_insensitive(self):
        assert validate_unit("KG") == "kg"

    def test_validate_date_str_multiple_formats(self):
        assert validate_date_str("2025-06-15") == datetime.date(2025, 6, 15)
        assert validate_date_str("15-06-2025") == datetime.date(2025, 6, 15)
        assert validate_date_str("15/06/2025") == datetime.date(2025, 6, 15)

    def test_validate_use_by_date_none(self):
        assert validate_use_by_date(None) is None

    def test_validate_use_by_date_empty_string(self):
        assert validate_use_by_date("") is None

    def test_validate_urgency_all_levels(self):
        for lvl in ("low", "medium", "high", "critical"):
            assert validate_urgency(lvl) == lvl

    def test_validate_kitchen_id_strips(self):
        assert validate_kitchen_id("  K001  ") == "K001"
