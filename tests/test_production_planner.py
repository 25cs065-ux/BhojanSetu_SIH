"""
Tests for Feature 7 — Data-Driven Production Planning
Run:  python -m pytest tests/test_production_planner.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.production_planner import (
    generate_recommendations,
    get_item_history,
    _analyse_surplus,
    _analyse_raw_material,
    _confidence_label,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

SURPLUS_RECORDS = [
    {"item_name": "Rice",      "quantity_kg": "5.0",  "date": "2025-01-10"},
    {"item_name": "Rice",      "quantity_kg": "3.5",  "date": "2025-01-17"},
    {"item_name": "Rice",      "quantity_kg": "4.0",  "date": "2025-01-24"},
    {"item_name": "Dal",       "quantity_kg": "2.0",  "date": "2025-01-12"},
    {"item_name": "Dal",       "quantity_kg": "1.5",  "date": "2025-01-19"},
    {"item_name": "Roti",      "quantity_kg": "1.0",  "date": "2025-01-14"},
    {"item_name": "Sabzi",     "quantity_kg": "0.5",  "date": "2025-01-15"},
    {"item_name": "Sabzi",     "quantity_kg": "0.8",  "date": "2025-01-22"},
    {"item_name": "Paneer",    "quantity_kg": "0.0",  "date": "2025-01-20"},  # zero — should NOT count
    {"item_name": "",          "quantity_kg": "2.0",  "date": "2025-01-20"},  # blank item
]

RAW_MATERIAL_RECORDS = [
    {"item_name": "Rice",  "quantity_kg": "50.0"},
    {"item_name": "Rice",  "quantity_kg": "50.0"},
    {"item_name": "Dal",   "quantity_kg": "20.0"},
    {"item_name": "Roti",  "quantity_kg": "10.0"},
]

RECORDS_MISSING_FIELDS = [
    {"quantity_kg": "3.0"},         # no item name
    {"item_name": "Rice"},          # no quantity
    {"item_name": "Dal", "quantity_kg": "bad_value"},
]


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — Valid historical records
# ──────────────────────────────────────────────────────────────────────────────
def test_valid_records_returns_ok_status():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        raw_material_records=RAW_MATERIAL_RECORDS,
    )
    assert result["metadata"]["status"] == "ok"


def test_valid_records_records_count():
    result = generate_recommendations(surplus_records=SURPLUS_RECORDS)
    assert result["records_analysed"] == len(SURPLUS_RECORDS)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — Empty history
# ──────────────────────────────────────────────────────────────────────────────
def test_empty_surplus_returns_no_data():
    result = generate_recommendations(surplus_records=[], raw_material_records=[])
    assert result["metadata"]["status"] == "no_data"
    assert result["recommendations"] == []
    assert result["records_analysed"] == 0


def test_none_surplus_with_missing_file():
    """When file does not exist, should return gracefully."""
    result = generate_recommendations(
        surplus_records=None,
        raw_material_records=None,
    )
    # Either ok (file has data) or no_data (file missing/empty) — must not raise
    assert result["metadata"]["status"] in ("ok", "no_data")


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — Missing/malformed fields
# ──────────────────────────────────────────────────────────────────────────────
def test_missing_item_name_skipped():
    result = generate_recommendations(surplus_records=RECORDS_MISSING_FIELDS)
    # 'Rice' row has no quantity; 'Dal' has bad quantity; blank item skipped
    # Should not crash
    assert result["metadata"]["status"] in ("ok", "no_data")


def test_bad_quantity_treated_as_zero():
    records = [{"item_name": "Rice", "quantity_kg": "not_a_number", "date": "2025-01-01"}]
    analysis = _analyse_surplus(records)
    # qty parsed as 0.0 → not counted as surplus
    assert "Rice" not in analysis or analysis.get("Rice", {}).get("surplus_occurrences", 0) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — Repeated surplus → recommendation generated
# ──────────────────────────────────────────────────────────────────────────────
def test_repeated_surplus_generates_recommendation():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    items_with_recs = [r["item"] for r in result["recommendations"]]
    assert "Rice" in items_with_recs, "Rice appears 3 times — must generate recommendation"


def test_recommendation_fields_present():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    for rec in result["recommendations"]:
        assert "item"           in rec
        assert "recommendation" in rec
        assert "reason"         in rec
        assert "evidence"       in rec
        assert "confidence"     in rec


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — No repeated surplus → no recommendation
# ──────────────────────────────────────────────────────────────────────────────
def test_no_repeated_surplus_below_threshold():
    single_records = [{"item_name": "Mango", "quantity_kg": "1.0", "date": "2025-01-01"}]
    result = generate_recommendations(
        surplus_records=single_records,
        min_occurrences=2,
    )
    items = [r["item"] for r in result["recommendations"]]
    assert "Mango" not in items


# ──────────────────────────────────────────────────────────────────────────────
# Test 6 — Recommendation content is accurate
# ──────────────────────────────────────────────────────────────────────────────
def test_rice_recommendation_text():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    rice_recs = [r for r in result["recommendations"] if r["item"] == "Rice"]
    assert len(rice_recs) == 1
    assert "Rice" in rice_recs[0]["recommendation"]
    assert "reduce" in rice_recs[0]["recommendation"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Test 7 — Evidence is grounded in actual records
# ──────────────────────────────────────────────────────────────────────────────
def test_rice_evidence_values():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    rice_recs = [r for r in result["recommendations"] if r["item"] == "Rice"]
    ev = rice_recs[0]["evidence"]
    assert ev["surplus_occurrences"] == 3          # 3 positive-qty Rice rows
    # total_records includes zero-qty Paneer and blank-item row
    assert ev["total_surplus_records_analysed"] == len(SURPLUS_RECORDS)
    assert 0 < ev["fraction_of_records"] <= 1


def test_raw_material_evidence_merged():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        raw_material_records=RAW_MATERIAL_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    rice_recs = [r for r in result["recommendations"] if r["item"] == "Rice"]
    ev = rice_recs[0]["evidence"]
    assert "total_procured_kg" in ev
    assert ev["total_procured_kg"] == 100.0   # 50 + 50


def test_date_range_in_evidence():
    result = generate_recommendations(
        surplus_records=SURPLUS_RECORDS,
        min_occurrences=2,
        min_fraction=0.0,
    )
    rice_recs = [r for r in result["recommendations"] if r["item"] == "Rice"]
    assert "2025-01-10" in rice_recs[0]["evidence"]["date_range"]
    assert "2025-01-24" in rice_recs[0]["evidence"]["date_range"]


# ──────────────────────────────────────────────────────────────────────────────
# Confidence label tests
# ──────────────────────────────────────────────────────────────────────────────
def test_confidence_high():
    assert _confidence_label(0.75) == "HIGH"

def test_confidence_medium():
    assert _confidence_label(0.45) == "MEDIUM"

def test_confidence_low():
    assert _confidence_label(0.15) == "LOW"

def test_confidence_weak():
    assert _confidence_label(0.05) == "WEAK"


# ──────────────────────────────────────────────────────────────────────────────
# get_item_history
# ──────────────────────────────────────────────────────────────────────────────
def test_get_item_history_found():
    hist = get_item_history("Rice", surplus_records=SURPLUS_RECORDS)
    assert hist["matching_records"] == 3
    assert hist["item"] == "Rice"

def test_get_item_history_not_found():
    hist = get_item_history("Imaginary_Item", surplus_records=SURPLUS_RECORDS)
    assert hist["matching_records"] == 0

def test_get_item_history_empty_data():
    hist = get_item_history("Rice", surplus_records=[])
    assert "No data" in hist["summary"]
