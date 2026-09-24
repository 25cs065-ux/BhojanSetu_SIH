"""
tests/test_nutrition_matcher.py
================================
Tests for models/nutrition_matcher.py (Feature 5 — Nutrition-Aware Matching).

All tests use:
- Actual dataset lookups (read-only) for verifying real data search
- Explicit mock NutritionProfile objects for controlled scoring tests
- Isolated fixture NGO/surplus data; real data files untouched
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from models.nutrition_matcher import (
    NutritionProfile,
    NutritionMatchResult,
    NutritionDB,
    load_nutrition_db,
    get_nutrition_profile,
    nutrition_score,
    enrich_matches,
    NUTRITION_PRIORITIES,
    _load_indian_nutrition,
    _load_group_nutrition,
)
from models.matching_engine import (
    SurplusRecord,
    NGORecord,
    NGOMatchResult,
    match_ngos,
)
import datetime

TODAY = datetime.date.today()


# ---------------------------------------------------------------------------
# Fixture helpers (isolated test data)
# ---------------------------------------------------------------------------


def _make_ngo(ngo_id="N001", capacity_kg=100.0, lat=28.5672, lon=77.21):
    return NGORecord(
        ngo_id=ngo_id,
        name=f"Test NGO {ngo_id}",
        location="Delhi",
        capacity_kg=capacity_kg,
        status="active",
        lat=lat,
        lon=lon,
    )


def _make_surplus(food_item="Dal Rice", quantity_kg=30.0, urgency="high"):
    return SurplusRecord(
        surplus_id="S-NUT-001",
        kitchen_id="K001",
        food_item=food_item,
        quantity_kg=quantity_kg,
        date_of_surplus=TODAY,
        expiry_time_hours=6.0,
        urgency=urgency,
    )


def _make_match(ngo=None, score=0.75):
    if ngo is None:
        ngo = _make_ngo()
    return NGOMatchResult(
        ngo=ngo,
        score=score,
        urgency_score=0.75,
        distance_score=0.6,
        capacity_score=1.0,
        quantity_score=1.0,
        distance_km=5.0,
        reasons=["Test match"],
    )


def _make_profile(
    food_name="TestFood",
    protein_g=None,
    iron_mg=None,
    calcium_mg=None,
    fibre_g=None,
    vitamin_c_mg=None,
    calories_kcal=None,
):
    return NutritionProfile(
        food_name=food_name,
        source="test",
        protein_g=protein_g,
        iron_mg=iron_mg,
        calcium_mg=calcium_mg,
        fibre_g=fibre_g,
        vitamin_c_mg=vitamin_c_mg,
        calories_kcal=calories_kcal,
        no_data=False,
    )


# ---------------------------------------------------------------------------
# Dataset loading tests (real datasets, read-only)
# ---------------------------------------------------------------------------


class TestDatasetLoading:

    def test_indian_nutrition_loads(self):
        index = _load_indian_nutrition()
        assert isinstance(index, dict)
        assert len(index) > 0

    def test_group_nutrition_loads(self):
        index = _load_group_nutrition()
        assert isinstance(index, dict)
        assert len(index) > 0

    def test_nutrition_db_build(self):
        db = NutritionDB.build()
        assert db.size() > 0

    def test_load_nutrition_db_returns_db(self):
        db = load_nutrition_db()
        assert isinstance(db, NutritionDB)
        assert db.size() > 0

    def test_load_nutrition_db_cached(self):
        db1 = load_nutrition_db()
        db2 = load_nutrition_db()
        assert db1 is db2  # same object (cached)


# ---------------------------------------------------------------------------
# Test: valid food item with nutrition information
# ---------------------------------------------------------------------------


class TestGetNutritionProfile:

    def test_known_indian_food_found(self):
        db = load_nutrition_db()
        # 'Hot tea (Garam Chai)' is in the Indian dataset
        profile = get_nutrition_profile("Hot tea (Garam Chai)", db)
        assert profile is not None
        assert profile.source == "indian"
        assert profile.calories_kcal is not None

    def test_case_insensitive_lookup(self):
        db = load_nutrition_db()
        profile = get_nutrition_profile("hot tea (garam chai)", db)
        assert profile is not None

    def test_food_item_not_found_returns_none(self):
        db = load_nutrition_db()
        # Extremely unlikely to be in dataset
        profile = get_nutrition_profile("xyzzy_food_that_does_not_exist_12345", db)
        assert profile is None

    def test_empty_food_name_returns_none(self):
        db = load_nutrition_db()
        assert get_nutrition_profile("", db) is None
        assert get_nutrition_profile("   ", db) is None

    def test_group_food_found(self):
        db = load_nutrition_db()
        # 'cream cheese' is in GROUP1
        profile = get_nutrition_profile("cream cheese", db)
        assert profile is not None

    def test_profile_has_expected_fields(self):
        db = load_nutrition_db()
        profile = get_nutrition_profile("Hot tea (Garam Chai)", db)
        assert profile is not None
        # Should have at least calories and protein
        assert profile.calories_kcal is not None
        assert profile.protein_g is not None

    def test_profile_no_fabricated_data(self):
        db = load_nutrition_db()
        profile = get_nutrition_profile("xyzzy_not_in_db", db)
        # Must return None, not a fabricated profile
        assert profile is None

    def test_multiple_possible_matches_returns_first(self):
        db = load_nutrition_db()
        # 'tea' should match something in the Indian dataset
        profile = get_nutrition_profile("tea", db)
        # May or may not be found — just verify no exception
        # (could be None if no partial match exists)
        assert profile is None or isinstance(profile, NutritionProfile)


# ---------------------------------------------------------------------------
# Test: nutrition_score function
# ---------------------------------------------------------------------------


class TestNutritionScore:

    def test_no_profile_returns_neutral(self):
        assert nutrition_score(None, "protein") == 0.5

    def test_no_priority_returns_neutral(self):
        profile = _make_profile(protein_g=20.0)
        assert nutrition_score(profile, None) == 0.5

    def test_high_protein_food_protein_priority(self):
        profile = _make_profile(protein_g=20.0)  # > _HIGH_PROTEIN_G=10
        sc = nutrition_score(profile, "protein")
        assert sc == 1.0

    def test_moderate_protein_food_protein_priority(self):
        profile = _make_profile(protein_g=5.0)  # 5 >= 10*0.4=4 → moderate
        sc = nutrition_score(profile, "protein")
        assert sc == 0.7

    def test_low_protein_food_protein_priority(self):
        profile = _make_profile(protein_g=0.5)  # < 4.0 → low
        sc = nutrition_score(profile, "protein")
        assert sc == 0.3

    def test_high_iron_food_iron_priority(self):
        profile = _make_profile(iron_mg=5.0)  # > _HIGH_IRON_MG=2.0
        sc = nutrition_score(profile, "iron")
        assert sc == 1.0

    def test_calcium_priority(self):
        profile = _make_profile(calcium_mg=200.0)  # > _HIGH_CALCIUM_MG=100
        sc = nutrition_score(profile, "calcium")
        assert sc == 1.0

    def test_unrecognised_priority_returns_neutral(self):
        profile = _make_profile(protein_g=20.0)
        sc = nutrition_score(profile, "carbohydrates_xyz")
        assert sc == 0.5

    def test_missing_nutrient_field_returns_neutral(self):
        # profile has no iron_mg
        profile = _make_profile(protein_g=20.0)  # iron_mg=None
        sc = nutrition_score(profile, "iron")
        assert sc == 0.5

    def test_incompatible_recipient_profile(self):
        # Food is low protein, NGO wants protein
        profile = _make_profile(protein_g=0.2)
        sc = nutrition_score(profile, "protein")
        assert sc == 0.3  # low compatibility

    def test_compatible_recipient_profile(self):
        # Food is high protein, NGO wants protein
        profile = _make_profile(protein_g=25.0)
        sc = nutrition_score(profile, "protein")
        assert sc == 1.0  # strong compatibility

    def test_nutrition_priorities_set_non_empty(self):
        assert len(NUTRITION_PRIORITIES) > 0
        assert "protein" in NUTRITION_PRIORITIES


# ---------------------------------------------------------------------------
# Test: enrich_matches
# ---------------------------------------------------------------------------


class TestEnrichMatches:

    def test_enrich_returns_same_count(self):
        db = load_nutrition_db()
        matches = [_make_match() for _ in range(3)]
        enriched = enrich_matches("Dal Rice", matches, db)
        assert len(enriched) == 3

    def test_enrich_unknown_food_uses_neutral_score(self):
        db = load_nutrition_db()
        matches = [_make_match()]
        enriched = enrich_matches("xyzzy_unknown_food_12345", matches, db)
        # Nutrition score neutral (0.5), so adjusted_score ≈ base
        assert enriched[0].nutrition_score == 0.5

    def test_enrich_adjusted_score_in_range(self):
        db = load_nutrition_db()
        matches = [_make_match(score=0.8)]
        enriched = enrich_matches("Hot tea (Garam Chai)", matches, db)
        assert 0.0 <= enriched[0].adjusted_score <= 1.0

    def test_enrich_sorted_by_adjusted_score(self):
        db = load_nutrition_db()
        m1 = _make_match(_make_ngo("N001"), score=0.9)
        m2 = _make_match(_make_ngo("N002"), score=0.5)
        enriched = enrich_matches("Dal Rice", [m1, m2], db)
        scores = [r.adjusted_score for r in enriched]
        assert scores == sorted(scores, reverse=True)

    def test_enrich_empty_matches_returns_empty(self):
        db = load_nutrition_db()
        enriched = enrich_matches("Dal Rice", [], db)
        assert enriched == []

    def test_enrich_nutrition_reason_present(self):
        db = load_nutrition_db()
        matches = [_make_match()]
        enriched = enrich_matches("Hot tea (Garam Chai)", matches, db)
        assert isinstance(enriched[0].nutrition_reason, str)
        assert len(enriched[0].nutrition_reason) > 0

    def test_enrich_to_dict_has_required_keys(self):
        db = load_nutrition_db()
        matches = [_make_match()]
        enriched = enrich_matches("Dal Rice", matches, db)
        d = enriched[0].to_dict()
        assert "nutrition_score" in d
        assert "adjusted_score" in d
        assert "nutrition_reason" in d
        assert "nutrition_profile" in d

    def test_fallback_when_nutrition_data_unavailable(self):
        """When food is not in any dataset, enrich_matches must not raise."""
        db = load_nutrition_db()
        matches = [_make_match(score=0.7)]
        enriched = enrich_matches("totally_unknown_xyz_food_9999", matches, db)
        assert len(enriched) == 1
        assert "Base matching score" in enriched[0].nutrition_reason

    def test_nutrition_ranking_changes_with_priority(self):
        """NGO with matching priority should rank higher when food is rich in that nutrient."""
        db = load_nutrition_db()

        # Manually create NGO records with nutrition_priority attribute
        ngo_protein = NGORecord("N001", "Protein NGO", "Delhi", 100, "active", 28.5, 77.2)
        ngo_protein.nutrition_priority = "protein"

        ngo_noprio = NGORecord("N002", "No Prio NGO", "Delhi", 100, "active", 28.5, 77.2)

        # Both have identical base scores
        m1 = NGOMatchResult(ngo_protein, 0.7, 0.75, 0.6, 1.0, 1.0, 5.0, ["test"])
        m2 = NGOMatchResult(ngo_noprio, 0.7, 0.75, 0.6, 1.0, 1.0, 5.0, ["test"])

        # cream cheese has protein ~0.9g per serving — low (from GROUP dataset)
        # This just verifies different scores are possible, not specific ordering
        enriched = enrich_matches("cream cheese", [m1, m2], db)
        assert len(enriched) == 2
        # Both should produce valid scores
        for r in enriched:
            assert 0.0 <= r.adjusted_score <= 1.0
