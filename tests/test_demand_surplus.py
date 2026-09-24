"""
Tests for demand_forecast.py and surplus_predictor.py
======================================================

Covers all 15 required test cases:
 1.  Dataset loading
 2.  Missing values check
 3.  Invalid week / empty input handling
 4.  Insufficient historical data (untrained model)
 5.  Valid model training
 6.  Valid prediction (single week)
 7.  Forecast output format validation
 8.  Forecast for multiple weeks (7 weeks)
 9.  Surplus calculation (basic arithmetic)
10.  Low surplus risk (< 10%)
11.  Medium surplus risk (10-25%)
12.  High surplus risk (> 25%)
13.  Invalid prepared quantity
14.  Missing forecast / invalid forecast_demand
15.  End-to-end demand -> surplus flow

Run with:
    uv run --with scikit-learn --with pandas --with numpy pytest tests/test_demand_surplus.py -v
"""

import sys
import os

# Make project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from models.demand_forecast import DemandForecaster
from models.surplus_predictor import SurplusPredictor


# ---------------------------------------------------------------------------
# Shared fixture: trained forecaster (expensive -- train once per session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def trained_forecaster():
    fc = DemandForecaster(n_estimators=50, random_state=42)  # fast for tests
    fc.train()
    return fc


# ---------------------------------------------------------------------------
# Test 1: Dataset loading
# ---------------------------------------------------------------------------

def test_dataset_loading():
    """Datasets must load without error and have expected columns."""
    train = pd.read_csv("datasets/train.csv")
    assert "num_orders" in train.columns, "num_orders column missing from train.csv"
    assert "week" in train.columns, "week column missing"
    assert "center_id" in train.columns
    assert "meal_id" in train.columns
    assert len(train) > 0, "train.csv is empty"

    meal_info = pd.read_csv("datasets/meal_info.csv")
    assert "meal_id" in meal_info.columns
    assert "category" in meal_info.columns

    center_info = pd.read_csv("datasets/fulfilment_center_info.csv")
    assert "center_id" in center_info.columns
    assert "center_type" in center_info.columns
    print("PASS: train=%d rows, meal_info=%d rows, center_info=%d rows" % (
        len(train), len(meal_info), len(center_info)))


# ---------------------------------------------------------------------------
# Test 2: Missing values check
# ---------------------------------------------------------------------------

def test_missing_values():
    """Core columns in train.csv must have zero missing values."""
    train = pd.read_csv("datasets/train.csv")
    required = ["num_orders", "week", "center_id", "meal_id",
                "checkout_price", "base_price"]
    for col in required:
        null_count = train[col].isnull().sum()
        assert null_count == 0, "Column '%s' has %d nulls" % (col, null_count)
    print("PASS: No missing values in core columns")


# ---------------------------------------------------------------------------
# Test 3: Invalid week / empty input handling
# ---------------------------------------------------------------------------

def test_empty_weeks_returns_empty_list(trained_forecaster):
    """
    Predict with empty weeks list must return [] without crashing.
    """
    results = trained_forecaster.predict(55, 1885, weeks=[])
    assert results == [], "Expected empty list for empty weeks, got %s" % results
    print("PASS: Empty weeks list returns []")


# ---------------------------------------------------------------------------
# Test 4: Insufficient historical data -- untrained model
# ---------------------------------------------------------------------------

def test_untrained_model_raises():
    """Calling predict on an untrained model must raise RuntimeError."""
    fc = DemandForecaster()
    with pytest.raises(RuntimeError, match="not trained"):
        fc.predict(55, 1885, [146])
    print("PASS: Untrained model raises RuntimeError")


# ---------------------------------------------------------------------------
# Test 5: Valid model training
# ---------------------------------------------------------------------------

def test_model_training(trained_forecaster):
    """Model must complete training and expose valid metrics."""
    assert trained_forecaster._trained is True
    assert trained_forecaster._model is not None
    metrics = trained_forecaster.get_metrics()
    assert "cv_mae" in metrics
    assert "cv_rmse" in metrics
    assert metrics["cv_mae"] > 0
    assert metrics["cv_rmse"] > 0
    print("PASS: Model trained. CV MAE=%.2f  CV RMSE=%.2f" % (
        metrics["cv_mae"], metrics["cv_rmse"]))
    print("      Baseline MAE=%.2f  RF better: %s" % (
        metrics["baseline_mae"], metrics["cv_mae"] < metrics["baseline_mae"]))


# ---------------------------------------------------------------------------
# Test 6: Valid prediction (single week)
# ---------------------------------------------------------------------------

def test_valid_prediction(trained_forecaster):
    """Single-week prediction must return a positive number."""
    results = trained_forecaster.predict(55, 1885, [146])
    assert len(results) == 1
    r = results[0]
    assert r["predicted_demand"] >= 0
    assert r["week"] == 146
    assert r["center_id"] == 55
    assert r["meal_id"] == 1885
    print("PASS: Prediction center=55 meal=1885 week=146: %.1f" % r["predicted_demand"])


# ---------------------------------------------------------------------------
# Test 7: Forecast output format
# ---------------------------------------------------------------------------

def test_forecast_output_format(trained_forecaster):
    """Output dict must contain all required keys."""
    results = trained_forecaster.predict(55, 1885, [146])
    required_keys = [
        "week", "center_id", "meal_id",
        "predicted_demand", "lower_bound", "upper_bound",
        "std_dev", "confidence_note",
    ]
    for key in required_keys:
        assert key in results[0], "Missing key: %s" % key
    assert results[0]["lower_bound"] <= results[0]["predicted_demand"]
    assert results[0]["upper_bound"] >= results[0]["predicted_demand"]
    print("PASS: Output format valid with all required keys")


# ---------------------------------------------------------------------------
# Test 8: Forecast for multiple weeks (7 weeks)
# ---------------------------------------------------------------------------

def test_forecast_multiple_weeks(trained_forecaster):
    """Predicting 7 weeks must return 7 records in correct week order."""
    weeks = list(range(146, 153))
    results = trained_forecaster.predict(55, 1885, weeks)
    assert len(results) == 7
    for i, r in enumerate(results):
        assert r["week"] == weeks[i]
        assert r["predicted_demand"] >= 0
    demands = [r["predicted_demand"] for r in results]
    print("PASS: 7-week forecast: %s" % demands)


# ---------------------------------------------------------------------------
# Test 9: Surplus calculation -- basic arithmetic
# ---------------------------------------------------------------------------

def test_surplus_calculation():
    """Surplus must equal prepared - forecast."""
    sp = SurplusPredictor()
    result = sp.calculate(prepared_qty=100.0, forecast_demand=82.0, item_name="Rice")
    assert result["estimated_surplus"] == pytest.approx(18.0, abs=0.01)
    assert result["surplus_pct"] == pytest.approx(18.0, abs=0.1)
    assert result["prepared_qty"] == 100.0
    assert result["forecast_demand"] == 82.0
    print("PASS: Surplus=18.0, pct=18.0%%, risk=%s" % result["risk_level"])


# ---------------------------------------------------------------------------
# Test 10: Low surplus risk (< 10%)
# ---------------------------------------------------------------------------

def test_low_surplus_risk():
    sp = SurplusPredictor()
    result = sp.calculate(100.0, 95.0)   # 5% surplus
    assert result["risk_level"] == "LOW"
    assert result["surplus_pct"] == pytest.approx(5.0, abs=0.1)
    print("PASS: 5%% surplus -> LOW risk")


# ---------------------------------------------------------------------------
# Test 11: Medium surplus risk (10-25%)
# ---------------------------------------------------------------------------

def test_medium_surplus_risk():
    sp = SurplusPredictor()
    result = sp.calculate(100.0, 82.0)   # 18% surplus
    assert result["risk_level"] == "MEDIUM"
    print("PASS: 18%% surplus -> MEDIUM risk")


# ---------------------------------------------------------------------------
# Test 12: High surplus risk (> 25%)
# ---------------------------------------------------------------------------

def test_high_surplus_risk():
    sp = SurplusPredictor()
    result = sp.calculate(100.0, 60.0)   # 40% surplus
    assert result["risk_level"] == "HIGH"
    assert result["surplus_pct"] == pytest.approx(40.0, abs=0.1)
    print("PASS: 40%% surplus -> HIGH risk")


# ---------------------------------------------------------------------------
# Test 13: Invalid prepared quantity
# ---------------------------------------------------------------------------

def test_invalid_prepared_quantity():
    sp = SurplusPredictor()
    with pytest.raises(ValueError, match="prepared_qty must be"):
        sp.calculate(prepared_qty=-5.0, forecast_demand=80.0)
    print("PASS: Negative prepared_qty raises ValueError")


# ---------------------------------------------------------------------------
# Test 14: Missing / invalid forecast_demand
# ---------------------------------------------------------------------------

def test_missing_forecast_raises():
    """Negative forecast_demand must raise ValueError."""
    sp = SurplusPredictor()
    with pytest.raises(ValueError, match="forecast_demand must be"):
        sp.calculate(prepared_qty=100.0, forecast_demand=-1.0)
    print("PASS: Negative forecast_demand raises ValueError")


# ---------------------------------------------------------------------------
# Test 15: End-to-end demand -> surplus flow
# ---------------------------------------------------------------------------

def test_end_to_end_flow(trained_forecaster):
    """Full flow: train -> predict -> surplus -> risk."""
    # 1. Get demand forecast for 3 weeks
    weeks = [146, 147, 148]
    forecasts = trained_forecaster.predict(center_id=55, meal_id=1885, weeks=weeks)
    assert len(forecasts) == 3

    # 2. Prepare 120 units for a forecast of 100 units => surplus = 20 units
    # surplus_pct = 20/120 * 100 = 16.67% => MEDIUM
    sp = SurplusPredictor()
    surplus_results = []
    for rec in forecasts:
        # Use an absolute over-preparation: prepared = forecast + 20% of forecast
        # so: prepared = 1.2 * forecast
        # surplus = prepared - forecast = 0.2 * forecast
        # surplus_pct = surplus / prepared * 100 = 0.2/1.2 * 100 = 16.67%
        prepared = rec["predicted_demand"] * 1.2
        result = sp.calculate(
            prepared_qty=prepared,
            forecast_demand=rec["predicted_demand"],
            item_name="Meal-1885",
            unit="portions",
            week=rec["week"],
            center_id=rec["center_id"],
            meal_id=rec["meal_id"],
            lower_bound=rec["lower_bound"],
            upper_bound=rec["upper_bound"],
        )
        surplus_results.append(result)

    # 3. All should be exactly 16.67% surplus => MEDIUM risk
    for r in surplus_results:
        assert r["risk_level"] == "MEDIUM", "Expected MEDIUM, got %s (pct=%.1f)" % (
            r["risk_level"], r["surplus_pct"])
        # surplus_pct = 0.2/1.2 * 100 = 16.67
        assert r["surplus_pct"] == pytest.approx(16.67, abs=0.1)

    # 4. Batch summarise
    summary = sp.summarise_batch(surplus_results)
    assert summary["overall_risk"] == "MEDIUM"
    assert summary["total_surplus"] > 0
    print("PASS: End-to-end verified. Batch summary: %s" % summary)

    # 5. Verify batch_calculate also works
    prepared_list = [rec["predicted_demand"] * 1.2 for rec in forecasts]
    batch = sp.batch_calculate(prepared_list, forecasts)
    assert len(batch) == 3
    print("PASS: batch_calculate returned %d results" % len(batch))


# ---------------------------------------------------------------------------
# Test bonus A: event calendar input
# ---------------------------------------------------------------------------

def test_event_calendar(trained_forecaster):
    """Event calendar affects event_multiplier in output."""
    events = [
        {"week": 147, "event_name": "Diwali", "event_type": "festival", "multiplier": 1.3}
    ]
    results = trained_forecaster.predict(55, 1885, [146, 147, 148], events=events)
    r147 = next(r for r in results if r["week"] == 147)
    assert r147["event_multiplier"] == pytest.approx(1.3, abs=0.01)
    r146 = next(r for r in results if r["week"] == 146)
    assert r146["event_multiplier"] == 1.0
    print("PASS: Event calendar applied: week 147 multiplier=1.3")


# ---------------------------------------------------------------------------
# Test bonus B: forecast_next_n_weeks convenience method
# ---------------------------------------------------------------------------

def test_forecast_next_n_weeks(trained_forecaster):
    """forecast_next_n_weeks(n=7) should return 7 future week forecasts."""
    results = trained_forecaster.forecast_next_n_weeks(55, 1885, n=7)
    assert len(results) == 7
    assert all(r["week"] > 145 for r in results)
    weeks = [r["week"] for r in results]
    print("PASS: Next 7 weeks forecast: %s" % weeks)
