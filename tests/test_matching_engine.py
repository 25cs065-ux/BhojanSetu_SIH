"""
tests/test_matching_engine.py
==============================
Tests for models/matching_engine.py (Feature 4 — NGO Matching).

All test data is isolated fixture data — the real data/ngos.json and
data/surplus_log.csv are never modified.
"""

import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from models.matching_engine import (
    SurplusRecord,
    NGORecord,
    NGOMatchResult,
    make_surplus_record,
    load_ngo_records,
    match_ngos,
    format_ngo_match_report,
    _capacity_score,
    _quantity_fit_score,
    _distance_score,
)

# ---------------------------------------------------------------------------
# Fixtures — clearly labelled, isolated test data
# ---------------------------------------------------------------------------

TODAY = datetime.date.today()


def _surplus(
    kitchen_id="K001",
    food_item="Dal Rice",
    quantity_kg=50.0,
    expiry_time_hours=6.0,
    urgency="high",
    surplus_id="S-TEST-001",
):
    return SurplusRecord(
        surplus_id=surplus_id,
        kitchen_id=kitchen_id,
        food_item=food_item,
        quantity_kg=quantity_kg,
        date_of_surplus=TODAY,
        expiry_time_hours=expiry_time_hours,
        urgency=urgency,
    )


def _ngo(
    ngo_id="N001",
    name="Test NGO A",
    capacity_kg=100.0,
    status="active",
    lat=28.5672,
    lon=77.2100,
):
    return NGORecord(
        ngo_id=ngo_id,
        name=name,
        location="Test Location",
        capacity_kg=capacity_kg,
        status=status,
        lat=lat,
        lon=lon,
    )


KITCHENS = {
    "K001": {"kitchen_id": "K001", "name": "IIT Delhi", "lat": 28.5450, "lon": 77.1926},
    "K002": {"kitchen_id": "K002", "name": "AIIMS", "lat": 28.5672, "lon": 77.2100},
}


# ---------------------------------------------------------------------------
# make_surplus_record
# ---------------------------------------------------------------------------


class TestMakeSurplusRecord:

    def test_valid_surplus_record(self):
        s = make_surplus_record(
            "K001", "Dal Rice", 50, TODAY.isoformat(), 6, "high"
        )
        assert s.kitchen_id == "K001"
        assert s.food_item == "Dal Rice"
        assert s.quantity_kg == 50.0
        assert s.expiry_time_hours == 6.0
        assert s.urgency == "high"
        assert s.status == "confirmed"
        assert s.surplus_id  # auto-generated

    def test_empty_kitchen_id_raises(self):
        with pytest.raises(ValueError):
            make_surplus_record("", "Dal Rice", 50, TODAY.isoformat(), 6, "high")

    def test_empty_food_item_raises(self):
        with pytest.raises(ValueError, match="empty"):
            make_surplus_record("K001", "  ", 50, TODAY.isoformat(), 6, "high")

    def test_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="positive"):
            make_surplus_record("K001", "Rice", -10, TODAY.isoformat(), 6, "high")

    def test_zero_expiry_raises(self):
        with pytest.raises(ValueError, match="positive"):
            make_surplus_record("K001", "Rice", 10, TODAY.isoformat(), 0, "high")

    def test_invalid_urgency_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            make_surplus_record("K001", "Rice", 10, TODAY.isoformat(), 6, "extreme")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            make_surplus_record("K001", "Rice", 10, "not-a-date", 6, "high")

    def test_surplus_to_dict(self):
        s = make_surplus_record("K001", "Dal", 30, TODAY.isoformat(), 4, "medium")
        d = s.to_dict()
        assert d["food_item"] == "Dal"
        assert d["quantity_kg"] == 30.0


# ---------------------------------------------------------------------------
# load_ngo_records
# ---------------------------------------------------------------------------


class TestLoadNGORecords:

    def test_valid_ngo_list(self):
        raw = [
            {
                "ngo_id": "N001",
                "name": "Test NGO",
                "location": "Delhi",
                "lat": 28.5,
                "lon": 77.2,
                "capacity_kg": 100,
                "status": "active",
            }
        ]
        records = load_ngo_records(raw)
        assert len(records) == 1
        assert records[0].ngo_id == "N001"
        assert records[0].is_available()

    def test_missing_ngo_id_skipped(self):
        raw = [{"name": "No ID NGO", "capacity_kg": 100, "status": "active"}]
        records = load_ngo_records(raw)
        assert records == []

    def test_inactive_ngo_loaded_but_not_available(self):
        raw = [
            {
                "ngo_id": "N002",
                "name": "Inactive NGO",
                "capacity_kg": 100,
                "status": "inactive",
                "location": "",
            }
        ]
        records = load_ngo_records(raw)
        assert len(records) == 1
        assert not records[0].is_available()

    def test_invalid_capacity_defaults_to_zero(self):
        raw = [
            {
                "ngo_id": "N003",
                "name": "Zero Cap",
                "capacity_kg": "bad_value",
                "status": "active",
                "location": "",
            }
        ]
        records = load_ngo_records(raw)
        assert records[0].capacity_kg == 0.0
        assert not records[0].is_available()

    def test_missing_coordinates_set_to_none(self):
        raw = [
            {
                "ngo_id": "N004",
                "name": "No Coords",
                "capacity_kg": 100,
                "status": "active",
                "location": "Unknown",
            }
        ]
        records = load_ngo_records(raw)
        assert records[0].lat is None
        assert records[0].lon is None

    def test_empty_list_returns_empty(self):
        assert load_ngo_records([]) == []


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------


class TestScoringHelpers:

    def test_capacity_score_sufficient(self):
        assert _capacity_score(100, 50) == 1.0

    def test_capacity_score_exact(self):
        assert _capacity_score(50, 50) == 1.0

    def test_capacity_score_partial(self):
        # 30/50 = 0.6 >= 0.5 → partial
        sc = _capacity_score(30, 50)
        assert 0.5 <= sc < 1.0

    def test_capacity_score_insufficient(self):
        # 10/50 = 0.2 < 0.5 → 0.0
        assert _capacity_score(10, 50) == 0.0

    def test_quantity_fit_score_within_capacity(self):
        assert _quantity_fit_score(100, 50) == 1.0

    def test_quantity_fit_score_exact(self):
        assert _quantity_fit_score(50, 50) == 1.0

    def test_quantity_fit_score_slight_excess(self):
        # 100 > 50 but ratio=2.0 ≤ 2.0 → 0.5
        assert _quantity_fit_score(50, 100) == 0.5

    def test_quantity_fit_score_large_excess(self):
        # 300 / 50 = 6.0 > 2.0 → 0.0
        assert _quantity_fit_score(50, 300) == 0.0

    def test_distance_score_zero_km(self):
        assert _distance_score(0.0, 50.0) == 1.0

    def test_distance_score_max(self):
        assert _distance_score(50.0, 50.0) == 0.0

    def test_distance_score_half(self):
        sc = _distance_score(25.0, 50.0)
        assert sc == pytest.approx(0.5)

    def test_distance_score_unknown(self):
        assert _distance_score(None, 50.0) == 0.5


# ---------------------------------------------------------------------------
# match_ngos — the main matching function
# ---------------------------------------------------------------------------


class TestMatchNGOs:

    def test_valid_surplus_returns_matches(self):
        surplus = _surplus()
        ngos = [_ngo("N001", capacity_kg=100)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert len(results) == 1
        assert results[0].ngo.ngo_id == "N001"

    def test_no_available_ngos_returns_empty(self):
        surplus = _surplus()
        ngos = []
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_inactive_ngo_excluded(self):
        surplus = _surplus()
        ngos = [_ngo("N005", status="inactive", capacity_kg=200)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_quantity_mismatch_excluded(self):
        # NGO capacity = 10, surplus = 100 → ratio 0.1 → filtered out
        surplus = _surplus(quantity_kg=100.0)
        ngos = [_ngo("N001", capacity_kg=10.0)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_sufficient_capacity_included(self):
        surplus = _surplus(quantity_kg=50.0)
        ngos = [_ngo("N001", capacity_kg=200.0)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert len(results) == 1

    def test_insufficient_capacity_excluded(self):
        # 15 kg capacity, 50 kg surplus → ratio 0.3 < 0.5 → excluded
        surplus = _surplus(quantity_kg=50.0)
        ngos = [_ngo("N001", capacity_kg=15.0)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_same_location_candidate(self):
        surplus = _surplus(kitchen_id="K001")
        # NGO at same coordinates as K001
        ngos = [_ngo("N001", lat=28.5450, lon=77.1926, capacity_kg=100)]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert len(results) == 1
        assert results[0].distance_km is not None
        assert results[0].distance_km == pytest.approx(0.0, abs=0.1)

    def test_distant_candidate_lower_score(self):
        surplus = _surplus(kitchen_id="K001")
        ngo_near = _ngo("N001", lat=28.5672, lon=77.2100, capacity_kg=100)  # ~3.5km
        ngo_far = _ngo("N002", lat=28.9000, lon=77.5000, capacity_kg=100)  # ~50+km
        results = match_ngos(surplus, [ngo_near, ngo_far], KITCHENS)
        assert len(results) >= 1
        # Near NGO should score higher
        ids = [r.ngo.ngo_id for r in results]
        assert ids[0] == "N001"

    def test_invalid_ngo_record_skipped(self):
        # An NGO with capacity=0 is filtered out
        surplus = _surplus()
        ngos = [NGORecord("N999", "Bad NGO", "Nowhere", 0.0, "active")]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_unavailable_ngo_excluded(self):
        surplus = _surplus()
        ngos = [_ngo("N001", status="inactive")]
        results = match_ngos(surplus, ngos, KITCHENS)
        assert results == []

    def test_ranking_best_first(self):
        surplus = _surplus(kitchen_id="K001")
        ngo_near = _ngo("N001", lat=28.5672, lon=77.2100, capacity_kg=200)
        ngo_far = _ngo("N002", lat=28.9000, lon=77.5000, capacity_kg=200)
        results = match_ngos(surplus, [ngo_far, ngo_near], KITCHENS)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_match_score_in_valid_range(self):
        surplus = _surplus()
        ngos = [_ngo()]
        results = match_ngos(surplus, ngos)
        assert 0.0 <= results[0].score <= 1.0

    def test_missing_optional_fields_handled(self):
        # NGO without lat/lon
        surplus = _surplus()
        ngo = NGORecord("N010", "No Coord NGO", "Somewhere", 100.0, "active")
        results = match_ngos(surplus, [ngo])
        assert len(results) == 1
        assert results[0].distance_km is None
        assert results[0].distance_score == 0.5

    def test_no_kitchens_dict_disables_distance(self):
        surplus = _surplus()
        ngos = [_ngo()]
        results = match_ngos(surplus, ngos, kitchens=None)
        assert results[0].distance_km is None

    def test_result_has_reasons(self):
        surplus = _surplus()
        ngos = [_ngo()]
        results = match_ngos(surplus, ngos)
        assert len(results[0].reasons) > 0

    def test_to_dict_structure(self):
        surplus = _surplus()
        ngos = [_ngo()]
        result = match_ngos(surplus, ngos)[0]
        d = result.to_dict()
        assert "ngo_id" in d
        assert "score" in d
        assert "reasons" in d

    def test_critical_urgency_score_higher(self):
        surplus_crit = _surplus(urgency="critical")
        surplus_low = _surplus(urgency="low")
        ngos = [_ngo()]
        r_crit = match_ngos(surplus_crit, ngos)
        r_low = match_ngos(surplus_low, ngos)
        assert r_crit[0].score > r_low[0].score

    def test_format_report_contains_food_item(self):
        surplus = _surplus()
        ngos = [_ngo()]
        matches = match_ngos(surplus, ngos)
        report = format_ngo_match_report(surplus, matches)
        assert "Dal Rice" in report

    def test_format_report_no_matches(self):
        surplus = _surplus()
        report = format_ngo_match_report(surplus, [])
        assert "No suitable NGO matches found" in report
