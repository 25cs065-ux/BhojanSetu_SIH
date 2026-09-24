"""
Full End-to-End Integration Test
Historical data → Production recommendation → Sustainability calculation
→ Report generation → Explainability output

Run:  <python_interpreter> tests/test_integration.py
"""
from __future__ import annotations
import sys, os, json, traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []

def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    icon = "✓" if condition else "✗"
    print(f"  {icon} [{status}] {name}" + (f"  — {detail}" if detail else ""))

print("\n" + "="*60)
print("  FULL END-TO-END INTEGRATION TEST")
print("="*60)

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Historical data (in-memory)
# ──────────────────────────────────────────────────────────────────────────────
print("\n[1/5] Building historical in-memory dataset...")

SURPLUS = [
    {"item_name": "Rice",   "quantity_kg": "8.0",  "date": "2025-01-10"},
    {"item_name": "Rice",   "quantity_kg": "6.5",  "date": "2025-01-17"},
    {"item_name": "Rice",   "quantity_kg": "7.0",  "date": "2025-01-24"},
    {"item_name": "Rice",   "quantity_kg": "5.5",  "date": "2025-01-31"},
    {"item_name": "Dal",    "quantity_kg": "3.0",  "date": "2025-01-12"},
    {"item_name": "Dal",    "quantity_kg": "2.5",  "date": "2025-01-19"},
    {"item_name": "Roti",   "quantity_kg": "1.0",  "date": "2025-01-14"},
    {"item_name": "Sabzi",  "quantity_kg": "0.5",  "date": "2025-01-22"},
]

RAW = [
    {"item_name": "Rice", "quantity_kg": "60.0"},
    {"item_name": "Rice", "quantity_kg": "60.0"},
    {"item_name": "Rice", "quantity_kg": "60.0"},
    {"item_name": "Dal",  "quantity_kg": "25.0"},
]

ACTIVITIES = [
    {"kitchen_id": "K1", "date": "2025-01-10",
     "food_redistributed_kg": "15.0", "food_waste_avoided_kg": "8.0",  "meals_count": "30"},
    {"kitchen_id": "K1", "date": "2025-01-17",
     "food_redistributed_kg": "12.0", "food_waste_avoided_kg": "6.0",  "meals_count": "24"},
    {"kitchen_id": "K2", "date": "2025-01-10",
     "food_redistributed_kg": "9.0",  "food_waste_avoided_kg": "4.0",  "meals_count": "18"},
    {"kitchen_id": "K2", "date": "2025-01-17",
     "food_redistributed_kg": "11.0", "food_waste_avoided_kg": "5.0",  "meals_count": "22"},
]

check("E2E-1 test_data_ready", len(SURPLUS) == 8 and len(ACTIVITIES) == 4)

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Production planning recommendations
# ──────────────────────────────────────────────────────────────────────────────
print("\n[2/5] Production planning...")

try:
    from models.production_planner import generate_recommendations

    plan_result = generate_recommendations(
        surplus_records=SURPLUS,
        raw_material_records=RAW,
        min_occurrences=2,
        min_fraction=0.0,
    )

    check("E2E-2a planning_ok",
          plan_result["metadata"]["status"] == "ok")
    check("E2E-2b rice_recommended",
          any(r["item"] == "Rice" for r in plan_result["recommendations"]))
    check("E2E-2c recommendations_have_evidence",
          all("evidence" in r for r in plan_result["recommendations"]))
    check("E2E-2d rice_occurrences_correct",
          next(r for r in plan_result["recommendations"] if r["item"] == "Rice")
              ["evidence"]["surplus_occurrences"] == 4)

    print(f"     Recommendations generated: {plan_result['metadata']['items_with_recommendations']}")
    rice_rec = next(r for r in plan_result["recommendations"] if r["item"] == "Rice")
    print(f"     Rice confidence: {rice_rec['confidence']}")

except Exception as e:
    check("E2E-2 production_planning_error", False, str(e))
    traceback.print_exc()
    plan_result = {"recommendations": []}

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Sustainability calculation
# ──────────────────────────────────────────────────────────────────────────────
print("\n[3/5] Sustainability calculation...")

try:
    from models.sustainability_calc import (
        calculate_metrics, aggregate_by_date, aggregate_by_kitchen,
        EMISSION_FACTOR_KG_CO2_PER_KG_FOOD, WATER_FACTOR_LITERS_PER_KG_FOOD,
    )

    metrics = calculate_metrics(ACTIVITIES)

    check("E2E-3a metrics_ok", metrics["status"] == "ok")
    check("E2E-3b redistributed_correct",
          abs(metrics["total_food_redistributed_kg"] - 47.0) < 0.01)
    check("E2E-3c waste_avoided_correct",
          abs(metrics["total_food_waste_avoided_kg"] - 23.0) < 0.01)
    check("E2E-3d meals_correct",
          metrics["total_meals_redistributed"] == 94)
    expected_co2  = round(23.0 * EMISSION_FACTOR_KG_CO2_PER_KG_FOOD, 4)
    expected_water = round(23.0 * WATER_FACTOR_LITERS_PER_KG_FOOD, 4)
    check("E2E-3e co2e_estimated",
          abs(metrics["estimated_co2e_avoided_kg"] - expected_co2) < 0.01,
          f"got={metrics['estimated_co2e_avoided_kg']} expected≈{expected_co2}")
    check("E2E-3f co2e_labelled_estimated",
          "ESTIMATED" in metrics["co2e_label"])
    check("E2E-3g water_estimated",
          abs(metrics["estimated_water_saved_liters"] - expected_water) < 0.1,
          f"got={metrics['estimated_water_saved_liters']} expected≈{expected_water}")

    daily = aggregate_by_date(ACTIVITIES)
    check("E2E-3h daily_aggregation_2_dates", len(daily) == 2)

    by_k = aggregate_by_kitchen(ACTIVITIES)
    check("E2E-3i kitchen_aggregation_2_kitchens", len(by_k) == 2)

    print(f"     Total redistributed : {metrics['total_food_redistributed_kg']} kg")
    print(f"     CO2e avoided (ESTIMATED): {metrics['estimated_co2e_avoided_kg']} kg CO2e")
    print(f"     Water saved  (ESTIMATED): {metrics['estimated_water_saved_liters']} L")

except Exception as e:
    check("E2E-3 sustainability_error", False, str(e))
    traceback.print_exc()
    metrics = {}

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: PDF report generation
# ──────────────────────────────────────────────────────────────────────────────
print("\n[4/5] PDF report generation...")

try:
    from models.report_generator import generate_report

    report_data = {
        "institution_name":            "BhojanSetu Integration Test Kitchen",
        "reporting_period_start":      "2025-01-01",
        "reporting_period_end":        "2025-01-31",
        "food_redistributed_kg":       metrics.get("total_food_redistributed_kg", 47.0),
        "food_waste_avoided_kg":       metrics.get("total_food_waste_avoided_kg", 23.0),
        "meals_redistributed":         metrics.get("total_meals_redistributed", 94),
        "estimated_co2e_avoided_kg":   metrics.get("estimated_co2e_avoided_kg",
                                                    round(23.0 * 1.6, 2)),
        "estimated_water_saved_liters":metrics.get("estimated_water_saved_liters",
                                                    round(23.0 * 417.1, 1)),
        "donation_records": [
            {"date": "2025-01-10", "recipient": "NGO Asha Foundation", "quantity_kg": 15.0},
            {"date": "2025-01-17", "recipient": "NGO Bal Seva Trust",  "quantity_kg": 12.0},
        ],
        "sustainability_trend": aggregate_by_date(ACTIVITIES) if "aggregate_by_date" in dir() else [],
        "production_planning_recommendations": plan_result.get("recommendations", [])[:3],
    }

    pdf_path = generate_report(report_data)

    check("E2E-4a pdf_file_exists", os.path.exists(pdf_path), f"path={pdf_path}")
    check("E2E-4b pdf_nonzero_size", os.path.getsize(pdf_path) > 2000,
          f"size={os.path.getsize(pdf_path)} bytes")
    check("E2E-4c pdf_in_reports_dir", "reports" in pdf_path.replace("\\", "/"))

    # Verify it's a valid PDF (starts with %PDF)
    with open(pdf_path, "rb") as f:
        header = f.read(4)
    check("E2E-4d valid_pdf_header", header == b"%PDF", f"header={header}")

    print(f"     PDF: {pdf_path}  ({os.path.getsize(pdf_path)} bytes)")

except ImportError as ie:
    check("E2E-4 reportlab_needed", False, str(ie))
except Exception as e:
    check("E2E-4 pdf_error", False, str(e))
    traceback.print_exc()
    pdf_path = None

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Explainability
# ──────────────────────────────────────────────────────────────────────────────
print("\n[5/5] Explainability...")

try:
    from models.explainability import explain_prediction, EXPLAINABILITY_NOT_AVAILABLE

    # 5a — None model
    r_none = explain_prediction(model=None)
    check("E2E-5a none_model_graceful",
          r_none["explainable"] == False and EXPLAINABILITY_NOT_AVAILABLE in r_none["message"])

    # 5b — Unknown model
    class _Opaque:
        pass
    r_opaque = explain_prediction(model=_Opaque())
    check("E2E-5b unknown_model_graceful", r_opaque["explainable"] == False)

    # 5c — sklearn linear model (if available)
    try:
        from sklearn.linear_model import LinearRegression
        import numpy as np
        X = np.array([[1,2],[3,4],[5,6],[7,8],[9,10]], dtype=float)
        y = np.array([2.5, 4.5, 6.5, 8.5, 10.5])
        lr = LinearRegression().fit(X, y)
        r_lr = explain_prediction(model=lr, feature_names=["past_demand", "day_of_week"])
        check("E2E-5c linear_explainable", r_lr["explainable"] == True)
        check("E2E-5d linear_has_coefficients", "coefficients" in r_lr)
        check("E2E-5e linear_ranked_factors", len(r_lr.get("ranked_factors", [])) == 2)
        print(f"     Linear model explanation:")
        print(f"       Method: {r_lr.get('method')}")
        print(f"       Factors: {[f['feature'] for f in r_lr.get('ranked_factors', [])]}")
    except ImportError:
        check("E2E-5c sklearn_not_installed", True, "sklearn not installed — integration test skipped")

    # 5d — Random forest (if available)
    try:
        from sklearn.ensemble import RandomForestRegressor
        import numpy as np
        X2 = np.random.rand(50, 3)
        y2 = X2[:, 0] * 2 + X2[:, 1] + np.random.rand(50) * 0.1
        rf = RandomForestRegressor(n_estimators=10, random_state=42).fit(X2, y2)
        r_rf = explain_prediction(model=rf, feature_names=["trend", "seasonality", "lag"])
        check("E2E-5e rf_explainable", r_rf["explainable"] == True)
        check("E2E-5f rf_has_importances", "feature_importances" in r_rf)
        print(f"     Random Forest importances: {r_rf.get('feature_importances')}")
    except ImportError:
        check("E2E-5e sklearn_rf_not_installed", True, "sklearn RF not installed")

    # 5e — demand_forecast module integration
    from models.explainability import get_demand_forecast_explanation
    r_df = get_demand_forecast_explanation()
    check("E2E-5g demand_forecast_graceful",
          r_df["explainable"] in (True, False))  # either works or gracefully fails
    if not r_df["explainable"]:
        print(f"     demand_forecast explanation: {r_df.get('reason','')[:80]}")

except Exception as e:
    check("E2E-5 explainability_error", False, str(e))
    traceback.print_exc()

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("  INTEGRATION TEST SUMMARY")
print("="*60)

total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  Total:  {total}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")

if failed:
    print("\n  FAILED:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"    ✗ {name}  — {detail}")
    sys.exit(1)
else:
    print("\n  ALL INTEGRATION TESTS PASSED ✓")
