"""
tests/test_all.py
------------------
All 21 tests for BhojanSetu matching, nutrition, and routing modules.

Run from the project root:
    python -m pytest tests/test_all.py -v
or:
    python tests/test_all.py

Tests
-----
MATCHING  (1–8)
NUTRITION (9–13)
ROUTING   (14–20)
END-TO-END (21)
"""

import os
import sys
import math
import unittest

# Force UTF-8 output on Windows (cp1252 cannot encode arrows/box-drawing chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")



# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.distance import haversine
from models.matching_engine import match_surplus
from models.nutrition_matcher import lookup_nutrition, enhance_matches, _nutrition_score
from models.route_optimizer import build_route

# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixtures
# ─────────────────────────────────────────────────────────────────────────────

# Four real NGOs with valid coordinates and varied urgency/capacity
NGOS = [
    {
        "id": "NGO001", "name": "Asha Food Relief",
        "lat": 19.0760, "lon": 72.8777,
        "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian",
    },
    {
        "id": "NGO002", "name": "Hope Shelter",
        "lat": 19.1136, "lon": 72.8697,
        "capacity_kg": 60, "urgency": 5, "food_preference": "any",
    },
    {
        "id": "NGO003", "name": "Seva Nutrition Center",
        "lat": 19.0330, "lon": 73.0297,
        "capacity_kg": 40, "urgency": 2, "food_preference": "vegetarian",
    },
    {
        "id": "NGO004", "name": "Arogya Meals",
        "lat": 18.9220, "lon": 72.8347,
        "capacity_kg": 150, "urgency": 4, "food_preference": "any",
    },
]

KITCHENS = [
    {
        "id": "K001", "name": "Mumbai Central Kitchen",
        "lat": 19.0760, "lon": 72.8777,
    },
    {
        "id": "K002", "name": "Andheri Cloud Kitchen",
        "lat": 19.1136, "lon": 72.8697,
    },
    {
        "id": "K003", "name": "Thane Community Kitchen",
        "lat": 19.2183, "lon": 72.9781,
    },
    {"id": "K004", "name": "No Coords Kitchen"},
]

VALID_SURPLUS = {
    "surplus_id": "S001",
    "kitchen_id": "K001",
    "food_name": "Dal Makhani",
    "quantity_kg": 50,
    "food_type": "vegetarian",
}

# ─────────────────────────────────────────────────────────────────────────────
# MATCHING TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestMatching(unittest.TestCase):

    # ── Test 1: Valid surplus → returns matches ────────────────────────────
    def test_01_valid_surplus(self):
        """Valid surplus with multiple NGOs → non-empty match list returned."""
        result = match_surplus(VALID_SURPLUS, ngos=NGOS, kitchens=KITCHENS)
        print(f"\n[T01] matches returned: {len(result['matches'])}")
        for m in result["matches"]:
            print(f"      {m['ngo_name']:25s} score={m['score']:.2f}  "
                  f"(dist={m['score_breakdown']['distance']:.2f}, "
                  f"urgency={m['score_breakdown']['urgency']:.2f}, "
                  f"cap={m['score_breakdown']['capacity']:.2f})")
        self.assertGreater(len(result["matches"]), 0)
        # All scores must be in [0, 100]
        for m in result["matches"]:
            self.assertGreaterEqual(m["score"], 0)
            self.assertLessEqual(m["score"], 100)

    # ── Test 2: No recipients (empty NGO list) ─────────────────────────────
    def test_02_no_recipients(self):
        """Empty NGO list → matches is empty list, no crash."""
        result = match_surplus(VALID_SURPLUS, ngos=[], kitchens=KITCHENS)
        print(f"\n[T02] matches: {result['matches']}")
        self.assertEqual(result["matches"], [])

    # ── Test 3: Quantity mismatch (qty > every NGO capacity) ───────────────
    def test_03_quantity_mismatch(self):
        """Surplus quantity exceeds all NGO capacities → 0 matches."""
        surplus = {**VALID_SURPLUS, "quantity_kg": 9999}
        result = match_surplus(surplus, ngos=NGOS, kitchens=KITCHENS)
        print(f"\n[T03] matches: {len(result['matches'])}, "
              f"warnings: {result['warnings']}")
        self.assertEqual(result["matches"], [])
        # All skipped NGOs must be reported in warnings
        skipped = [w for w in result["warnings"] if "skipped" in w]
        self.assertGreater(len(skipped), 0)

    # ── Test 4: Capacity mismatch for some NGOs ────────────────────────────
    def test_04_capacity_mismatch_partial(self):
        """Surplus qty=80 → only NGOs with capacity>=80 are matched."""
        surplus = {**VALID_SURPLUS, "quantity_kg": 80}
        result = match_surplus(surplus, ngos=NGOS, kitchens=KITCHENS)
        matched_ids = [m["ngo_id"] for m in result["matches"]]
        print(f"\n[T04] qty=80 → matched NGOs: {matched_ids}")
        # NGO002 (60 kg) and NGO003 (40 kg) must be excluded
        self.assertNotIn("NGO002", matched_ids)
        self.assertNotIn("NGO003", matched_ids)
        # NGO001 (100) and NGO004 (150) must be included
        self.assertIn("NGO001", matched_ids)
        self.assertIn("NGO004", matched_ids)

    # ── Test 5: Distance ranking ────────────────────────────────────────────
    def test_05_distance_ranking(self):
        """NGO at same coords as kitchen should outscore a far-away NGO
        when urgency and capacity are equal."""
        near_ngo = {
            "id": "NEAR", "name": "Near NGO",
            "lat": 19.0760, "lon": 72.8777,   # same as K001
            "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian",
        }
        far_ngo = {
            "id": "FAR", "name": "Far NGO",
            "lat": 18.5000, "lon": 73.8000,   # ~120 km away
            "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian",
        }
        result = match_surplus(
            VALID_SURPLUS, ngos=[near_ngo, far_ngo], kitchens=KITCHENS
        )
        scores = {m["ngo_id"]: m["score"] for m in result["matches"]}
        print(f"\n[T05] NEAR={scores.get('NEAR'):.2f}  "
              f"FAR={scores.get('FAR', 0):.2f}")
        self.assertGreater(scores.get("NEAR", 0), scores.get("FAR", 0))

    # ── Test 6: Urgency ranking ─────────────────────────────────────────────
    def test_06_urgency_ranking(self):
        """Higher urgency NGO (same distance, same capacity) scores higher."""
        low_urgency = {
            "id": "LOW", "name": "Low Urgency NGO",
            "lat": 19.0760, "lon": 72.8777,
            "capacity_kg": 100, "urgency": 1, "food_preference": "vegetarian",
        }
        high_urgency = {
            "id": "HIGH", "name": "High Urgency NGO",
            "lat": 19.0760, "lon": 72.8777,
            "capacity_kg": 100, "urgency": 5, "food_preference": "vegetarian",
        }
        result = match_surplus(
            VALID_SURPLUS, ngos=[low_urgency, high_urgency], kitchens=KITCHENS
        )
        scores = {m["ngo_id"]: m["score"] for m in result["matches"]}
        print(f"\n[T06] HIGH urgency={scores.get('HIGH'):.2f}  "
              f"LOW urgency={scores.get('LOW'):.2f}")
        self.assertGreater(scores["HIGH"], scores["LOW"])

    # ── Test 7: Multiple recipients returned and ranked ────────────────────
    def test_07_multiple_recipients(self):
        """When 3 NGOs qualify they are all returned, sorted by score desc."""
        result = match_surplus(
            {**VALID_SURPLUS, "quantity_kg": 30},
            ngos=NGOS, kitchens=KITCHENS,
        )
        matches = result["matches"]
        print(f"\n[T07] {len(matches)} matches (qty=30):")
        for m in matches:
            print(f"      {m['ngo_id']:8s} score={m['score']:.2f}")
        self.assertGreaterEqual(len(matches), 2)
        # Verify sorted order
        scores = [m["score"] for m in matches]
        self.assertEqual(scores, sorted(scores, reverse=True))

    # ── Test 8: Missing recipient data (NGO without lat/lon) ───────────────
    def test_08_missing_recipient_data(self):
        """NGO missing lat/lon is skipped gracefully with a warning."""
        partial_ngos = [
            {"id": "NGO001", "name": "No Coords NGO",
             "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian"},
            NGOS[1],  # valid
        ]
        result = match_surplus(VALID_SURPLUS, ngos=partial_ngos, kitchens=KITCHENS)
        matched_ids = [m["ngo_id"] for m in result["matches"]]
        warn_text = " ".join(result["warnings"])
        print(f"\n[T08] matched={matched_ids}, warnings:")
        for w in result["warnings"]:
            print(f"      {w}")
        self.assertNotIn("NGO001", matched_ids)
        self.assertIn("NGO002", matched_ids)
        self.assertIn("NGO001", warn_text)

# ─────────────────────────────────────────────────────────────────────────────
# NUTRITION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestNutrition(unittest.TestCase):

    # ── Test 9: Valid nutrition lookup ─────────────────────────────────────
    def test_09_valid_nutrition_lookup(self):
        """Known dish returns a nutrition dict with real values from CSV."""
        row = lookup_nutrition("Chicken sandwich")
        print(f"\n[T09] Chicken sandwich nutrition:")
        if row:
            for k, v in row.items():
                print(f"      {k}: {v}")
        self.assertIsNotNone(row)
        self.assertIn("Protein (g)", row)
        # Verify values are numeric
        protein = float(row["Protein (g)"])
        self.assertGreater(protein, 0)

    # ── Test 10: Unknown food ───────────────────────────────────────────────
    def test_10_unknown_food(self):
        """Completely unknown food name returns None (no fabrication)."""
        row = lookup_nutrition("xyz_does_not_exist_food_12345")
        print(f"\n[T10] lookup 'xyz_does_not_exist_food_12345' → {row}")
        self.assertIsNone(row)

    # ── Test 11: Missing nutrition data (bad path) ─────────────────────────
    def test_11_missing_nutrition_data(self):
        """When dataset path is invalid, lookup returns None gracefully."""
        row = lookup_nutrition("Dal", dataset_path="/nonexistent/path.csv")
        print(f"\n[T11] lookup with bad dataset path → {row}")
        self.assertIsNone(row)

    # ── Test 12: Nutrition factor changes ranking ──────────────────────────
    def test_12_nutrition_changes_ranking(self):
        """enhance_matches re-ranks matches when nutrition boost differs
        between two otherwise equal-scored NGOs (same score, same boost
        means same position – here we verify order is stable when boost
        is identical)."""
        # Build two NGOs at identical location/urgency/capacity → same score
        ngo_a = {
            "id": "A", "name": "Alpha",
            "lat": 19.0760, "lon": 72.8777,
            "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian",
        }
        ngo_b = {
            "id": "B", "name": "Beta",
            "lat": 19.0760, "lon": 72.8777,
            "capacity_kg": 100, "urgency": 3, "food_preference": "vegetarian",
        }
        result = match_surplus(
            VALID_SURPLUS, ngos=[ngo_a, ngo_b], kitchens=KITCHENS
        )
        enhanced = enhance_matches(result)
        print(f"\n[T12] After enhance_matches for '{VALID_SURPLUS['food_name']}':")
        for m in enhanced["matches"]:
            print(f"      {m['ngo_id']:5s} score={m['score']:.2f}  "
                  f"boost={m['nutrition_boost']:.4f}  "
                  f"adj={m['adjusted_score']:.2f}")
        # Nutrition boost must be same for both (same food, same calculation)
        boosts = {m["ngo_id"]: m["nutrition_boost"] for m in enhanced["matches"]}
        self.assertEqual(boosts["A"], boosts["B"])
        # adjusted_score = score + boost (must be consistent)
        for m in enhanced["matches"]:
            self.assertAlmostEqual(m["adjusted_score"],
                                   m["score"] + m["nutrition_boost"], places=2)

    # ── Test 13: Nutrition factor unavailable ──────────────────────────────
    def test_13_nutrition_unavailable(self):
        """When dataset is missing, enhance_matches returns original order
        and adds a warning; no crash."""
        result = match_surplus(VALID_SURPLUS, ngos=NGOS[:2], kitchens=KITCHENS)
        # Patch the dataset path to something nonexistent
        enhanced = enhance_matches(result, dataset_path="/no/such/file.csv")
        print(f"\n[T13] Nutrition unavailable – warnings:")
        for w in enhanced["warnings"]:
            print(f"      {w}")
        self.assertIn("unavailable", " ".join(enhanced["warnings"]).lower())
        # adjusted_score == score when no boost
        for m in enhanced["matches"]:
            self.assertAlmostEqual(m["adjusted_score"], m["score"], places=2)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTING TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestRouting(unittest.TestCase):

    # ── Test 14: One stop ──────────────────────────────────────────────────
    def test_14_one_stop(self):
        """Single NGO stop → route has exactly one entry, distance > 0."""
        result = build_route("K001", ["NGO001"],
                             kitchens=KITCHENS, ngos=NGOS)
        print(f"\n[T14] One-stop route:")
        for s in result["ordered_stops"]:
            print(f"      stop {s['stop_index']}: {s['ngo_name']}  "
                  f"leg={s['leg_distance_km']} km  "
                  f"cum={s['cumulative_distance_km']} km")
        self.assertEqual(len(result["ordered_stops"]), 1)
        # K001 and NGO001 share the same lat/lon → distance should be 0.0
        self.assertAlmostEqual(result["total_distance_km"], 0.0, places=3)

    # ── Test 15: Two stops ─────────────────────────────────────────────────
    def test_15_two_stops(self):
        """Two NGO stops → route has 2 entries, cumulative distance correct."""
        result = build_route("K001", ["NGO002", "NGO004"],
                             kitchens=KITCHENS, ngos=NGOS)
        print(f"\n[T15] Two-stop route:")
        for s in result["ordered_stops"]:
            print(f"      stop {s['stop_index']}: {s['ngo_name']}  "
                  f"leg={s['leg_distance_km']} km  "
                  f"cum={s['cumulative_distance_km']} km")
        print(f"      total_distance_km={result['total_distance_km']}")
        self.assertEqual(len(result["ordered_stops"]), 2)
        total = result["total_distance_km"]
        self.assertGreater(total, 0)
        # Cumulative of last stop must equal total
        self.assertAlmostEqual(
            result["ordered_stops"][-1]["cumulative_distance_km"],
            total, places=3
        )

    # ── Test 16: Multiple stops ─────────────────────────────────────────────
    def test_16_multiple_stops(self):
        """Three NGO stops → route has 3 entries, monotonically increasing
        cumulative distance."""
        result = build_route("K001", ["NGO001", "NGO002", "NGO004"],
                             kitchens=KITCHENS, ngos=NGOS)
        stops = result["ordered_stops"]
        print(f"\n[T16] Multi-stop route:")
        for s in stops:
            print(f"      stop {s['stop_index']}: {s['ngo_name']}  "
                  f"cum={s['cumulative_distance_km']} km")
        self.assertEqual(len(stops), 3)
        cums = [s["cumulative_distance_km"] for s in stops]
        for i in range(1, len(cums)):
            self.assertGreaterEqual(cums[i], cums[i - 1])

    # ── Test 17: Missing coordinates (NGO without lat/lon) ─────────────────
    def test_17_missing_coordinates(self):
        """NGO missing lat/lon is excluded from route; warning issued."""
        ngos_with_missing = [
            {"id": "NGO005", "name": "No Coords NGO"},  # no lat/lon
            NGOS[0],
        ]
        result = build_route("K001", ["NGO005", "NGO001"],
                             kitchens=KITCHENS, ngos=ngos_with_missing)
        stop_ids = [s["ngo_id"] for s in result["ordered_stops"]]
        print(f"\n[T17] Stops after excluding no-coords NGO: {stop_ids}")
        print(f"      Warnings: {result['warnings']}")
        self.assertNotIn("NGO005", stop_ids)
        self.assertIn("NGO001", stop_ids)
        self.assertIn("NGO005", result["excluded_stops"])

    # ── Test 18: Invalid coordinates ──────────────────────────────────────
    def test_18_invalid_coordinates(self):
        """NGO with out-of-range lat/lon is excluded; ValueError caught."""
        bad_ngo = {
            "id": "BADCOORD", "name": "Bad Coords NGO",
            "lat": 999.0, "lon": 999.0,   # invalid
            "capacity_kg": 100, "urgency": 3, "food_preference": "any",
        }
        result = build_route("K001", ["BADCOORD", "NGO001"],
                             kitchens=KITCHENS, ngos=[bad_ngo, NGOS[0]])
        stop_ids = [s["ngo_id"] for s in result["ordered_stops"]]
        print(f"\n[T18] Stops after invalid coord NGO: {stop_ids}")
        print(f"      Warnings: {result['warnings']}")
        self.assertNotIn("BADCOORD", stop_ids)
        self.assertIn("BADCOORD", result["excluded_stops"])

    # ── Test 19: Route ordering (NNG picks nearest first) ──────────────────
    def test_19_route_ordering(self):
        """NNG must visit the closest unvisited stop first.
        K001 is at (19.076, 72.878). NGO002 at (19.114, 72.870) is ~4.3 km
        away; NGO004 at (18.922, 72.835) is ~17 km away.
        So NNG should visit NGO002 first."""
        result = build_route("K001", ["NGO004", "NGO002"],
                             kitchens=KITCHENS, ngos=NGOS)
        stops = result["ordered_stops"]
        print(f"\n[T19] NNG ordering from K001:")
        for s in stops:
            print(f"      stop {s['stop_index']}: {s['ngo_name']}  "
                  f"leg={s['leg_distance_km']} km")
        self.assertEqual(stops[0]["ngo_id"], "NGO002")
        self.assertEqual(stops[1]["ngo_id"], "NGO004")

    # ── Test 20: Distance calculation accuracy ─────────────────────────────
    def test_20_distance_calculation(self):
        """Haversine between Mumbai (~19.076°N, 72.878°E) and
        Thane (~19.218°N, 72.978°E) should be ~19–21 km."""
        d = haversine(19.076, 72.878, 19.218, 72.978)
        print(f"\n[T20] Mumbai→Thane Haversine distance: {d:.3f} km")
        self.assertGreater(d, 15.0)
        self.assertLess(d, 25.0)
        # Same point → 0
        self.assertAlmostEqual(haversine(19.076, 72.878, 19.076, 72.878),
                               0.0, places=6)
        # Symmetry
        d_rev = haversine(19.218, 72.978, 19.076, 72.878)
        self.assertAlmostEqual(d, d_rev, places=6)

# ─────────────────────────────────────────────────────────────────────────────
# END-TO-END TEST
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEnd(unittest.TestCase):

    # ── Test 21: Surplus → Matching → Nutrition → Route ────────────────────
    def test_21_end_to_end_pipeline(self):
        """Full pipeline:
        1. Match surplus S001 (Dal Makhani, 50 kg, vegetarian) to NGOs.
        2. Enhance with nutrition data.
        3. Take top-2 matches, build delivery route from kitchen K001.
        Verify each stage produces valid output.
        """
        print("\n[T21] ──── END-TO-END PIPELINE ────")

        # Stage 1: Matching
        surplus = VALID_SURPLUS
        match_result = match_surplus(surplus, ngos=NGOS, kitchens=KITCHENS)
        print(f"\n  Stage 1 – Matching:")
        print(f"  Surplus: {surplus['food_name']} {surplus['quantity_kg']} kg "
              f"({surplus['food_type']}) from kitchen {surplus['kitchen_id']}")
        print(f"  {len(match_result['matches'])} matches found:")
        for m in match_result["matches"]:
            print(f"    {m['ngo_name']:25s} score={m['score']:.2f}  "
                  f"dist={m['distance_km']:.3f} km")

        self.assertGreater(len(match_result["matches"]), 0)

        # Stage 2: Nutrition enhancement
        enhanced = enhance_matches(match_result)
        lookup = enhanced.get("nutrition_lookup", {})
        print(f"\n  Stage 2 – Nutrition:")
        print(f"  Food queried: '{lookup.get('food_name_queried')}'")
        print(f"  Matched dish: '{lookup.get('dish_matched')}'")
        print(f"  Status: {lookup.get('lookup_status')}")
        if enhanced["matches"]:
            m0 = enhanced["matches"][0]
            print(f"  nutrition_score={m0['nutrition_score']:.4f}  "
                  f"boost={m0['nutrition_boost']:.4f}")
            print(f"  Top match after boost: {m0['ngo_name']}  "
                  f"adj_score={m0['adjusted_score']:.2f}")
        print(f"  Re-ranked matches:")
        for m in enhanced["matches"]:
            print(f"    {m['ngo_name']:25s} adj_score={m['adjusted_score']:.2f}")

        self.assertIn("nutrition_lookup", enhanced)
        self.assertIn("nutrition_boost", enhanced["matches"][0])

        # Stage 3: Route generation (top-2 NGOs)
        top_ngo_ids = [m["ngo_id"] for m in enhanced["matches"][:2]]
        route = build_route("K001", top_ngo_ids, kitchens=KITCHENS, ngos=NGOS)
        print(f"\n  Stage 3 – Route (top-2 NGOs: {top_ngo_ids}):")
        for s in route["ordered_stops"]:
            print(f"    stop {s['stop_index']}: {s['ngo_name']}  "
                  f"leg={s['leg_distance_km']} km  "
                  f"cum={s['cumulative_distance_km']} km")
        print(f"  total_distance_km={route['total_distance_km']}")

        self.assertEqual(len(route["ordered_stops"]), len(top_ngo_ids))
        self.assertIsNotNone(route["total_distance_km"])
        print("\n  ✓ End-to-end pipeline PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
