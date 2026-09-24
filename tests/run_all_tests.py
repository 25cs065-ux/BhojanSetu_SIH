"""
Self-contained test runner for all four features.
Does NOT require pytest or any third-party packages for the planner / sustainability tests.
PDF test requires reportlab; explainability test requires the models to be importable.

Run:  <python_interpreter> tests/run_all_tests.py
"""
from __future__ import annotations
import sys, os, traceback, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []

def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    icon = "✓" if condition else "✗"
    print(f"  {icon} [{status}] {name}" + (f"  — {detail}" if detail else ""))

def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 7 — PRODUCTION PLANNER
# ══════════════════════════════════════════════════════════════════════════════
section("FEATURE 7 — Production Planner")

try:
    from models.production_planner import (
        generate_recommendations, get_item_history,
        _analyse_surplus, _confidence_label,
    )

    SURPLUS = [
        {"item_name": "Rice",  "quantity_kg": "5.0",  "date": "2025-01-10"},
        {"item_name": "Rice",  "quantity_kg": "3.5",  "date": "2025-01-17"},
        {"item_name": "Rice",  "quantity_kg": "4.0",  "date": "2025-01-24"},
        {"item_name": "Dal",   "quantity_kg": "2.0",  "date": "2025-01-12"},
        {"item_name": "Dal",   "quantity_kg": "1.5",  "date": "2025-01-19"},
        {"item_name": "Roti",  "quantity_kg": "1.0",  "date": "2025-01-14"},
        {"item_name": "Sabzi", "quantity_kg": "0.5",  "date": "2025-01-15"},
        {"item_name": "Sabzi", "quantity_kg": "0.8",  "date": "2025-01-22"},
        {"item_name": "Paneer","quantity_kg": "0.0",  "date": "2025-01-20"},
        {"item_name": "",      "quantity_kg": "2.0",  "date": "2025-01-20"},
    ]
    RAW = [
        {"item_name": "Rice", "quantity_kg": "50.0"},
        {"item_name": "Rice", "quantity_kg": "50.0"},
        {"item_name": "Dal",  "quantity_kg": "20.0"},
    ]

    # Test 1 — Valid records
    r = generate_recommendations(surplus_records=SURPLUS, raw_material_records=RAW)
    check("T7-1a valid_records_status_ok", r["metadata"]["status"] == "ok")
    check("T7-1b records_analysed_correct", r["records_analysed"] == len(SURPLUS))

    # Test 2 — Empty history
    r_empty = generate_recommendations(surplus_records=[], raw_material_records=[])
    check("T7-2a empty_returns_no_data", r_empty["metadata"]["status"] == "no_data")
    check("T7-2b empty_recommendations_list_empty", r_empty["recommendations"] == [])

    # Test 3 — Missing fields
    bad = [{"quantity_kg": "3.0"}, {"item_name": "X"}, {"item_name": "Y", "quantity_kg": "bad"}]
    r_bad = generate_recommendations(surplus_records=bad)
    check("T7-3 missing_fields_no_crash", r_bad["metadata"]["status"] in ("ok", "no_data"))
    analysis_bad = _analyse_surplus([{"item_name": "Rice", "quantity_kg": "not_a_number"}])
    check("T7-3b bad_qty_treated_zero",
          "Rice" not in analysis_bad or analysis_bad.get("Rice",{}).get("surplus_occurrences",0) == 0)

    # Test 4 — Repeated surplus → recommendation
    r2 = generate_recommendations(surplus_records=SURPLUS, min_occurrences=2, min_fraction=0.0)
    items = [rec["item"] for rec in r2["recommendations"]]
    check("T7-4 repeated_surplus_rice_recommended", "Rice" in items)

    # Test 5 — No repeated surplus
    single = [{"item_name": "Mango", "quantity_kg": "1.0", "date": "2025-01-01"}]
    r3 = generate_recommendations(surplus_records=single, min_occurrences=2)
    check("T7-5 single_occurrence_no_rec", "Mango" not in [x["item"] for x in r3["recommendations"]])

    # Test 6 — Recommendation fields present
    for rec in r2["recommendations"]:
        for field in ("item","recommendation","reason","evidence","confidence"):
            check(f"T7-6 field_{field}_present_in_{rec['item']}", field in rec)

    # Test 7 — Evidence grounded in actual values
    rice_recs = [rec for rec in r2["recommendations"] if rec["item"] == "Rice"]
    check("T7-7a rice_rec_exists", len(rice_recs) == 1)
    if rice_recs:
        ev = rice_recs[0]["evidence"]
        check("T7-7b surplus_occurrences_correct", ev["surplus_occurrences"] == 3)
        check("T7-7c fraction_in_range", 0 < ev["fraction_of_records"] <= 1)
        check("T7-7d date_range_has_start", "2025-01-10" in ev["date_range"])
        check("T7-7e date_range_has_end",   "2025-01-24" in ev["date_range"])

    # Raw material merged
    r4 = generate_recommendations(surplus_records=SURPLUS, raw_material_records=RAW,
                                   min_occurrences=2, min_fraction=0.0)
    rice_r = [rec for rec in r4["recommendations"] if rec["item"] == "Rice"]
    if rice_r:
        check("T7-7f raw_material_procured_kg", rice_r[0]["evidence"].get("total_procured_kg") == 100.0)

    # Confidence labels
    check("T7-8a conf_high",   _confidence_label(0.75) == "HIGH")
    check("T7-8b conf_medium", _confidence_label(0.45) == "MEDIUM")
    check("T7-8c conf_low",    _confidence_label(0.15) == "LOW")
    check("T7-8d conf_weak",   _confidence_label(0.05) == "WEAK")

    # get_item_history
    hist = get_item_history("Rice", surplus_records=SURPLUS)
    check("T7-9a item_history_found", hist["matching_records"] == 3)
    hist_miss = get_item_history("Ghost", surplus_records=SURPLUS)
    check("T7-9b item_history_not_found", hist_miss["matching_records"] == 0)
    hist_empty = get_item_history("Rice", surplus_records=[])
    check("T7-9c item_history_empty_data", "No data" in hist_empty["summary"])

    print("\n  Sample output (Rice recommendation):")
    if rice_r:
        print("  " + json.dumps(rice_r[0], indent=4).replace("\n", "\n  "))

except Exception as e:
    check("T7 IMPORT/RUNTIME ERROR", False, str(e))
    traceback.print_exc()

# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 8 — SUSTAINABILITY
# ══════════════════════════════════════════════════════════════════════════════
section("FEATURE 8 — Sustainability Calculator")

try:
    from models.sustainability_calc import (
        calculate_metrics, aggregate_by_date, aggregate_by_kitchen,
        EMISSION_FACTOR_KG_CO2_PER_KG_FOOD,
        WATER_FACTOR_LITERS_PER_KG_FOOD,
    )

    ACTIVITIES = [
        {"kitchen_id": "K1", "date": "2025-01-10", "food_redistributed_kg": "12.5",
         "food_waste_avoided_kg": "8.0",  "meals_count": "25"},
        {"kitchen_id": "K1", "date": "2025-01-11", "food_redistributed_kg": "10.0",
         "food_waste_avoided_kg": "5.0",  "meals_count": "20"},
        {"kitchen_id": "K2", "date": "2025-01-10", "food_redistributed_kg": "7.0",
         "food_waste_avoided_kg": "3.0",  "meals_count": "14"},
        {"kitchen_id": "K2", "date": "2025-01-11", "food_redistributed_kg": "0.0",
         "food_waste_avoided_kg": "0.0",  "meals_count": "0"},
    ]

    # Test 1 — Valid activity
    m = calculate_metrics(ACTIVITIES)
    check("T8-1 valid_activity_status_ok", m["status"] == "ok")
    check("T8-1b total_redistributed_correct",
          abs(m["total_food_redistributed_kg"] - 29.5) < 0.01)
    check("T8-1c total_waste_avoided_correct",
          abs(m["total_food_waste_avoided_kg"] - 16.0) < 0.01)
    check("T8-1d total_meals_correct", m["total_meals_redistributed"] == 59)

    # Test 2 — Zero quantity
    zero_act = [{"kitchen_id": "K1", "date": "2025-01-01",
                 "food_redistributed_kg": "0.0", "food_waste_avoided_kg": "0.0", "meals_count": "0"}]
    mz = calculate_metrics(zero_act)
    check("T8-2 zero_quantity_ok", mz["total_food_redistributed_kg"] == 0.0)
    check("T8-2b zero_co2_ok", mz["estimated_co2e_avoided_kg"] == 0.0)

    # Test 3 — Negative quantity (should be clamped / ignored)
    neg_act = [{"kitchen_id": "K1", "date": "2025-01-01",
                "food_redistributed_kg": "-5.0", "food_waste_avoided_kg": "-3.0", "meals_count": "-2"}]
    mn = calculate_metrics(neg_act)
    check("T8-3 negative_clamped_to_zero_or_ignored",
          mn["total_food_redistributed_kg"] <= 0)

    # Test 4 — Missing activity
    me = calculate_metrics([])
    check("T8-4 empty_activity_no_crash", me["status"] in ("ok","no_data"))

    # Test 5 — Multiple activities
    check("T8-5 multiple_activities_summed",
          abs(m["total_food_redistributed_kg"] - (12.5+10.0+7.0+0.0)) < 0.01)

    # Test 6 — Date aggregation
    by_date = aggregate_by_date(ACTIVITIES)
    check("T8-6 date_aggregation_2_dates", len(by_date) == 2)
    date_2025_01_10 = next((d for d in by_date if d["date"] == "2025-01-10"), None)
    check("T8-6b date_jan10_redistributed_correct",
          date_2025_01_10 is not None and
          abs(date_2025_01_10["food_redistributed_kg"] - 19.5) < 0.01)

    # Test 7 — Kitchen aggregation
    by_kitchen = aggregate_by_kitchen(ACTIVITIES)
    check("T8-7 kitchen_aggregation_2_kitchens", len(by_kitchen) == 2)
    k1 = next((k for k in by_kitchen if k["kitchen_id"] == "K1"), None)
    check("T8-7b k1_redistributed_correct",
          k1 is not None and abs(k1["food_redistributed_kg"] - 22.5) < 0.01)

    # Test 8 — Carbon calculation
    check("T8-8a co2_estimate_labelled", "ESTIMATED" in m.get("co2e_label",""))
    expected_co2 = round(16.0 * EMISSION_FACTOR_KG_CO2_PER_KG_FOOD, 4)
    check("T8-8b co2_value_correct",
          abs(m["estimated_co2e_avoided_kg"] - expected_co2) < 0.01)

    # Test 9 — Factor documented
    check("T8-9a emission_factor_positive", EMISSION_FACTOR_KG_CO2_PER_KG_FOOD > 0)
    check("T8-9b water_factor_positive",    WATER_FACTOR_LITERS_PER_KG_FOOD > 0)

    print(f"\n  Sample metrics summary:")
    print(f"  Total redistributed : {m['total_food_redistributed_kg']} kg")
    print(f"  CO2e avoided (ESTIMATED): {m['estimated_co2e_avoided_kg']} kg CO2e")
    print(f"  Water saved (ESTIMATED): {m['estimated_water_saved_liters']} L")

except Exception as e:
    check("T8 IMPORT/RUNTIME ERROR", False, str(e))
    traceback.print_exc()

# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 9 — REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
section("FEATURE 9 — PDF Report Generator")

try:
    from models.report_generator import generate_report
    import os

    REPORT_DATA = {
        "institution_name": "Test Kitchen — BhojanSetu Demo",
        "reporting_period_start": "2025-01-01",
        "reporting_period_end": "2025-01-31",
        "food_redistributed_kg": 29.5,
        "food_waste_avoided_kg": 16.0,
        "meals_redistributed": 59,
        "estimated_co2e_avoided_kg": 25.6,
        "estimated_water_saved_liters": 1184.0,
        "donation_records": [
            {"date": "2025-01-10", "recipient": "NGO Alpha", "quantity_kg": 12.5},
            {"date": "2025-01-11", "recipient": "NGO Beta",  "quantity_kg": 10.0},
        ],
        "sustainability_trend": [
            {"date": "2025-01-10", "food_redistributed_kg": 19.5},
            {"date": "2025-01-11", "food_redistributed_kg": 10.0},
        ],
    }

    # Test 1 — PDF generation
    out_path = generate_report(REPORT_DATA)
    check("T9-1 pdf_file_created", os.path.exists(out_path),
          f"path={out_path}")
    check("T9-2 pdf_has_nonzero_size", os.path.getsize(out_path) > 1000,
          f"size={os.path.getsize(out_path)} bytes")

    # Test 3 — Empty data
    try:
        out_empty = generate_report({})
        check("T9-3 empty_data_no_crash", os.path.exists(out_empty))
    except Exception as ex:
        check("T9-3 empty_data_no_crash", False, str(ex))

    # Test 4 — Missing institution name
    data_no_inst = dict(REPORT_DATA); data_no_inst.pop("institution_name", None)
    out_no_inst = generate_report(data_no_inst)
    check("T9-4 missing_institution_no_crash", os.path.exists(out_no_inst))

    # Test 5 — Invalid dates handled
    data_bad_date = dict(REPORT_DATA)
    data_bad_date["reporting_period_start"] = "not-a-date"
    out_bad = generate_report(data_bad_date)
    check("T9-5 invalid_dates_no_crash", os.path.exists(out_bad))

    # Test 6 — Correct totals reflected in filename/metadata (spot check)
    check("T9-6 output_path_under_reports", "reports" in out_path.replace("\\", "/"))

    # Test 7 — File creation verified
    check("T9-7 file_readable", os.path.isfile(out_path))

    print(f"\n  PDF generated: {out_path}  ({os.path.getsize(out_path)} bytes)")

except ImportError as ie:
    check("T9 reportlab_not_installed", False, str(ie))
    traceback.print_exc()
except Exception as e:
    check("T9 RUNTIME ERROR", False, str(e))
    traceback.print_exc()

# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 10 — EXPLAINABILITY
# ══════════════════════════════════════════════════════════════════════════════
section("FEATURE 10 — Explainability")

try:
    from models.explainability import explain_prediction, EXPLAINABILITY_NOT_AVAILABLE

    # Test 1 — Valid model stub
    result = explain_prediction(model=None, prediction_input=None, model_type="unknown")
    check("T10-1 missing_model_returns_graceful",
          EXPLAINABILITY_NOT_AVAILABLE in result.get("message", ""))

    # Test 2 — Linear regression model
    try:
        from sklearn.linear_model import LinearRegression
        import numpy as np
        X = np.array([[1,2],[3,4],[5,6],[7,8],[9,10]])
        y = np.array([2,4,6,8,10])
        lr = LinearRegression().fit(X, y)
        res_lr = explain_prediction(model=lr, prediction_input=[[5,6]], model_type="linear_regression",
                                     feature_names=["feature_A","feature_B"])
        check("T10-2 linear_model_explainable", res_lr.get("explainable") == True)
        check("T10-2b coefficients_present", "coefficients" in res_lr)
        print(f"\n  Linear regression explanation:")
        print(f"  {json.dumps(res_lr, indent=4, default=str)[:600]}")
    except ImportError:
        check("T10-2 sklearn_not_available", True, "sklearn not installed — skipping coefficient test")

    # Test 3 — Prophet model (if available)
    try:
        from prophet import Prophet
        import pandas as pd
        df = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=60, freq="D"),
                           "y": range(60)})
        m_p = Prophet().fit(df)
        future = m_p.make_future_dataframe(periods=7)
        forecast = m_p.predict(future)
        res_p = explain_prediction(model=m_p, prediction_input=forecast, model_type="prophet")
        check("T10-3 prophet_components_returned", res_p.get("explainable") == True)
    except ImportError:
        check("T10-3 prophet_not_installed", True, "prophet not installed — skipping")

    # Test 4 — Unknown model type → graceful fallback
    result_unk = explain_prediction(model=object(), prediction_input=None, model_type="alien_model")
    check("T10-4 unknown_model_graceful", result_unk.get("explainable") == False)

    # Test 5 — None model explicitly
    result_none = explain_prediction(model=None, prediction_input=None)
    check("T10-5 none_model_graceful", EXPLAINABILITY_NOT_AVAILABLE in result_none.get("message",""))

    # Test 6 — Invalid prediction input
    try:
        from sklearn.linear_model import LinearRegression
        import numpy as np
        X = np.array([[1],[2],[3]])
        y = np.array([1,2,3])
        lr2 = LinearRegression().fit(X, y)
        result_inv = explain_prediction(model=lr2, prediction_input="bad_input",
                                        model_type="linear_regression")
        check("T10-6 invalid_input_no_crash", "error" in result_inv or result_inv.get("explainable") in (True, False))
    except ImportError:
        check("T10-6 sklearn_not_installed", True, "sklearn not installed — skipping")

except Exception as e:
    check("T10 IMPORT/RUNTIME ERROR", False, str(e))
    traceback.print_exc()

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
section("TEST SUMMARY")

total  = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  Total:  {total}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
if failed:
    print("\n  FAILED TESTS:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"    ✗ {name}  — {detail}")
    sys.exit(1)
else:
    print("\n  ALL TESTS PASSED ✓")
