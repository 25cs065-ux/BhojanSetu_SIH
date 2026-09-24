"""
tests/test_route_optimizer.py
==============================
Tests for models/route_optimizer.py (Feature 6 — Route Optimization).

All tests use isolated fixture data. Real data files are never modified.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from models.route_optimizer import (
    RouteStop,
    OptimizedRoute,
    build_stops_from_matches,
    build_stops_from_dicts,
    optimize_route,
    format_route_report,
    _distance_between,
)
from models.matching_engine import NGORecord, NGOMatchResult


# ---------------------------------------------------------------------------
# Fixture helpers (isolated test data — real Delhi coordinates)
# ---------------------------------------------------------------------------


def _stop(
    stop_id="S1",
    name="Stop 1",
    lat=28.5450,
    lon=77.1926,
    stop_type="ngo",
    urgency="medium",
    is_depot=False,
):
    return RouteStop(
        stop_id=stop_id,
        name=name,
        lat=lat,
        lon=lon,
        stop_type=stop_type,
        urgency=urgency,
        is_depot=is_depot,
    )


def _depot(lat=28.5450, lon=77.1926):
    return RouteStop(
        stop_id="K001",
        name="IIT Delhi Kitchen",
        lat=lat,
        lon=lon,
        stop_type="kitchen",
        urgency="medium",
        is_depot=True,
    )


def _no_coord_stop(stop_id="NC1", name="No Coords Stop"):
    return RouteStop(
        stop_id=stop_id,
        name=name,
        lat=None,
        lon=None,
        stop_type="ngo",
        urgency="medium",
        is_depot=False,
    )


def _make_ngo(ngo_id, lat, lon, capacity_kg=100.0):
    return NGORecord(
        ngo_id=ngo_id,
        name=f"NGO {ngo_id}",
        location="Delhi",
        capacity_kg=capacity_kg,
        status="active",
        lat=lat,
        lon=lon,
    )


def _make_ngo_match(ngo):
    return NGOMatchResult(
        ngo=ngo,
        score=0.8,
        urgency_score=0.75,
        distance_score=0.6,
        capacity_score=1.0,
        quantity_score=1.0,
        distance_km=5.0,
        reasons=["test"],
    )


KITCHEN_DICT = {
    "kitchen_id": "K001",
    "name": "IIT Delhi Kitchen",
    "lat": 28.5450,
    "lon": 77.1926,
}


# ---------------------------------------------------------------------------
# RouteStop tests
# ---------------------------------------------------------------------------


class TestRouteStop:

    def test_has_coordinates_true(self):
        s = _stop()
        assert s.has_coordinates() is True

    def test_has_coordinates_false(self):
        s = _no_coord_stop()
        assert s.has_coordinates() is False

    def test_to_dict_structure(self):
        s = _stop()
        d = s.to_dict()
        assert "stop_id" in d
        assert "lat" in d
        assert "lon" in d
        assert "is_depot" in d


# ---------------------------------------------------------------------------
# build_stops_from_matches
# ---------------------------------------------------------------------------


class TestBuildStopsFromMatches:

    def test_builds_depot_plus_ngo_stops(self):
        ngo = _make_ngo("N001", 28.5672, 77.21)
        matches = [_make_ngo_match(ngo)]
        stops = build_stops_from_matches(KITCHEN_DICT, matches, "high")
        assert len(stops) == 2
        assert stops[0].is_depot is True
        assert stops[0].stop_type == "kitchen"
        assert stops[1].stop_type == "ngo"

    def test_no_matches_only_depot(self):
        stops = build_stops_from_matches(KITCHEN_DICT, [], "high")
        assert len(stops) == 1
        assert stops[0].is_depot is True

    def test_urgency_propagated_to_ngo_stops(self):
        ngo = _make_ngo("N001", 28.5672, 77.21)
        matches = [_make_ngo_match(ngo)]
        stops = build_stops_from_matches(KITCHEN_DICT, matches, "critical")
        assert stops[1].urgency == "critical"


# ---------------------------------------------------------------------------
# build_stops_from_dicts
# ---------------------------------------------------------------------------


class TestBuildStopsFromDicts:

    def test_valid_dicts(self):
        dicts = [
            {"stop_id": "K1", "name": "Kitchen", "lat": 28.5, "lon": 77.2, "is_depot": True},
            {"stop_id": "N1", "name": "NGO 1", "lat": 28.6, "lon": 77.3},
        ]
        stops = build_stops_from_dicts(dicts)
        assert len(stops) == 2
        assert stops[0].is_depot is True

    def test_missing_coords_allowed(self):
        dicts = [{"stop_id": "X1", "name": "No Coord"}]
        stops = build_stops_from_dicts(dicts)
        assert stops[0].lat is None

    def test_empty_list(self):
        assert build_stops_from_dicts([]) == []


# ---------------------------------------------------------------------------
# _distance_between
# ---------------------------------------------------------------------------


class TestDistanceBetween:

    def test_distance_calculated(self):
        a = _stop(lat=28.5450, lon=77.1926)
        b = _stop(lat=28.5672, lon=77.2100)
        d = _distance_between(a, b)
        assert d is not None
        assert d > 0

    def test_zero_distance_same_point(self):
        a = _stop(lat=28.5450, lon=77.1926)
        b = _stop(lat=28.5450, lon=77.1926)
        d = _distance_between(a, b)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_missing_coords_returns_none(self):
        a = _no_coord_stop()
        b = _stop()
        assert _distance_between(a, b) is None
        assert _distance_between(b, a) is None

    def test_both_missing_coords(self):
        a = _no_coord_stop("NC1")
        b = _no_coord_stop("NC2")
        assert _distance_between(a, b) is None


# ---------------------------------------------------------------------------
# optimize_route — core algorithm tests
# ---------------------------------------------------------------------------


class TestOptimizeRoute:

    def test_single_stop_depot_only(self):
        stops = [_depot()]
        route = optimize_route(stops)
        assert len(route.stops) == 1
        assert route.total_km == 0.0
        assert route.segment_km == []
        assert route.cumulative_km == [0.0]

    def test_one_destination(self):
        depot = _depot()
        ngo = _stop("N1", "NGO 1", lat=28.5672, lon=77.2100)
        route = optimize_route([depot, ngo])
        assert len(route.stops) == 2
        assert route.total_km > 0
        assert len(route.segment_km) == 1
        assert route.segment_km[0] is not None

    def test_multiple_destinations(self):
        depot = _depot()
        n1 = _stop("N1", "NGO 1", lat=28.5672, lon=77.21)
        n2 = _stop("N2", "NGO 2", lat=28.6315, lon=77.2167)
        n3 = _stop("N3", "NGO 3", lat=28.6520, lon=77.19)
        route = optimize_route([depot, n1, n2, n3])
        assert len(route.stops) == 4
        assert route.total_km > 0
        assert len(route.segment_km) == 3
        assert len(route.cumulative_km) == 4

    def test_cumulative_km_non_decreasing(self):
        depot = _depot()
        stops = [
            depot,
            _stop("N1", lat=28.5672, lon=77.21),
            _stop("N2", lat=28.6315, lon=77.2167),
        ]
        route = optimize_route(stops)
        for i in range(len(route.cumulative_km) - 1):
            assert route.cumulative_km[i] <= route.cumulative_km[i + 1]

    def test_valid_coordinates(self):
        depot = _depot(28.5450, 77.1926)
        ngo = _stop("N1", lat=28.5672, lon=77.21)
        route = optimize_route([depot, ngo])
        assert route.warnings == []

    def test_invalid_coordinates_handled(self):
        # Stops without coordinates generate a warning, not an error
        depot = _depot()
        no_coord = _no_coord_stop()
        route = optimize_route([depot, no_coord])
        assert len(route.warnings) > 0
        assert no_coord in route.stops

    def test_missing_coordinates_appended_at_end(self):
        depot = _depot()
        coord_stop = _stop("N1", lat=28.5672, lon=77.21)
        no_coord = _no_coord_stop()
        route = optimize_route([depot, coord_stop, no_coord])
        # Stop with no coords should be last
        assert route.stops[-1].stop_id == no_coord.stop_id

    def test_duplicate_coordinates(self):
        # Two stops at same location should both appear
        depot = _depot(28.5450, 77.1926)
        n1 = _stop("N1", lat=28.5450, lon=77.1926)
        n2 = _stop("N2", lat=28.5450, lon=77.1926)
        route = optimize_route([depot, n1, n2])
        assert len(route.stops) == 3

    def test_empty_stops(self):
        route = optimize_route([])
        assert route.total_km == 0.0
        assert len(route.warnings) > 0

    def test_route_ordering_nearest_neighbour(self):
        # N1 is very close to depot; N3 is far; N2 is moderate
        # NNG should visit N1 first
        depot = _depot(28.5450, 77.1926)
        n1 = _stop("N1", lat=28.5500, lon=77.1950)  # very close (~0.7 km)
        n2 = _stop("N2", lat=28.6315, lon=77.2167)  # ~11 km
        n3 = _stop("N3", lat=28.9000, lon=77.5000)  # very far
        route = optimize_route([depot, n3, n2, n1], urgency_first=False)
        # First non-depot stop should be N1 (closest)
        assert route.stops[1].stop_id == "N1"

    def test_urgency_first_places_critical_before_distant(self):
        depot = _depot(28.5450, 77.1926)
        n_close = _stop("N_CLOSE", lat=28.5500, lon=77.1950, urgency="medium")
        n_crit = _stop("N_CRIT", lat=28.9000, lon=77.5000, urgency="critical")
        route = optimize_route([depot, n_close, n_crit], urgency_first=True)
        # Critical stop should come before close non-urgent stop
        stop_ids = [s.stop_id for s in route.stops]
        assert stop_ids.index("N_CRIT") < stop_ids.index("N_CLOSE")

    def test_urgency_first_false_uses_pure_nn(self):
        depot = _depot(28.5450, 77.1926)
        n_close = _stop("N_CLOSE", lat=28.5500, lon=77.1950, urgency="medium")
        n_crit = _stop("N_CRIT", lat=28.9000, lon=77.5000, urgency="critical")
        route = optimize_route([depot, n_close, n_crit], urgency_first=False)
        # Without urgency_first, nearest comes first
        assert route.stops[1].stop_id == "N_CLOSE"

    def test_distance_calculations_use_haversine(self):
        depot = _depot(28.5450, 77.1926)
        ngo = _stop("N1", lat=28.5672, lon=77.21)
        route = optimize_route([depot, ngo])
        # Known distance IIT Delhi ↔ AIIMS is approximately 3-4 km
        assert 2.0 < route.total_km < 6.0

    def test_total_km_equals_sum_of_segments(self):
        depot = _depot()
        stops = [depot, _stop("N1", lat=28.5672, lon=77.21), _stop("N2", lat=28.63, lon=77.22)]
        route = optimize_route(stops)
        seg_sum = sum(d for d in route.segment_km if d is not None)
        assert route.total_km == pytest.approx(seg_sum, abs=0.001)

    def test_output_serializable(self):
        depot = _depot()
        ngo = _stop("N1", lat=28.5672, lon=77.21)
        route = optimize_route([depot, ngo])
        d = route.to_dict()
        assert "total_km" in d
        assert "stops" in d
        assert "algorithm" in d
        assert "warnings" in d
        # Each stop has required fields
        for s in d["stops"]:
            assert "stop_id" in s
            assert "lat" in s
            assert "lon" in s


# ---------------------------------------------------------------------------
# format_route_report
# ---------------------------------------------------------------------------


class TestFormatRouteReport:

    def test_report_contains_total_distance(self):
        depot = _depot()
        ngo = _stop("N1", lat=28.5672, lon=77.21)
        route = optimize_route([depot, ngo])
        report = format_route_report(route)
        assert "Total distance" in report
        assert "km" in report

    def test_report_contains_stop_names(self):
        depot = _depot()
        ngo = _stop("N1", name="Test NGO", lat=28.5672, lon=77.21)
        route = optimize_route([depot, ngo])
        report = format_route_report(route)
        assert "Test NGO" in report

    def test_empty_route_report(self):
        route = optimize_route([])
        report = format_route_report(route)
        assert "No stops" in report

    def test_report_with_warnings(self):
        depot = _depot()
        no_coord = _no_coord_stop()
        route = optimize_route([depot, no_coord])
        report = format_route_report(route)
        assert "Warnings" in report


# ---------------------------------------------------------------------------
# build_stops_from_matches with NutritionMatchResult
# ---------------------------------------------------------------------------


class TestBuildStopsFromNutritionMatches:

    def test_nutrition_match_result_supported(self):
        """NutritionMatchResult objects must also work with build_stops_from_matches."""
        from models.nutrition_matcher import NutritionMatchResult, NutritionProfile

        ngo = _make_ngo("N001", 28.5672, 77.21)
        base_match = _make_ngo_match(ngo)
        profile = NutritionProfile("Dal Rice", source="indian", protein_g=5.0)
        nut_match = NutritionMatchResult(
            base_match=base_match,
            nutrition_profile=profile,
            nutrition_score=0.7,
            adjusted_score=0.8,
            nutrition_priority=None,
            nutrition_reason="Test reason",
        )
        stops = build_stops_from_matches(KITCHEN_DICT, [nut_match], "high")
        assert len(stops) == 2
        assert stops[1].stop_id == "N001"
