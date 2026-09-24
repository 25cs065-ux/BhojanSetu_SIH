"""
Sustainability & Carbon Impact Calculator — Feature 8
Calculates environmental metrics from food redistribution and waste-avoidance activity.

Methodology
-----------
Emission factor (kg CO2e per kg food):
  Derived from the median Total_emissions value across 43 food products in
  datasets/Food_Production.csv  (Our World in Data / Poore & Nemecek 2018).
  Median used (not mean) to avoid skew from outliers like beef/dark chocolate.
  Calculated: sorted 43 values → 22nd value = 1.6 kg CO2e/kg  (verified 2025).
  Source: Poore, J. & Nemecek, T. (2018). Reducing food's environmental impacts
          through producers and consumers. Science, 360(6392), 987-992.
          https://science.sciencemag.org/content/360/6392/987
  Unit: kg CO2e per kg of food

Water saving factor (liters per kg food):
  Derived from the median "Freshwater withdrawals per kilogram" column across
  products that have this value populated in Food_Production.csv (38 products).
  Median = 417.1 liters per kg  (verified 2025).
  Source: Same dataset (Poore & Nemecek 2018 via Our World in Data).
  Unit: liters per kg of food

Meals factor (kg food per meal):
  Assumed average meal size = 0.5 kg (approx. 500 g portion, consistent with
  FSSAI and WHO institutional meal norms). Configurable.
  Source: WHO / FSSAI institutional serving guidance.
  Unit: kg per meal

NOTE: All calculated environmental values are ESTIMATED.
They are order-of-magnitude estimates for awareness and trend tracking only.
They are NOT scientifically measured values and should NOT be cited as such.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets")

SUSTAINABILITY_LOG_PATH = os.path.join(DATA_DIR, "sustainability_log.csv")
EXCHANGE_LOG_PATH       = os.path.join(DATA_DIR, "exchange_log.csv")
FOOD_PRODUCTION_PATH    = os.path.join(DATASET_DIR, "Food_Production.csv")

# ──────────────────────────────────────────────────────────────────────────────
# Environmental conversion factors (configurable constants)
#
# Source: Median of Total_emissions column from datasets/Food_Production.csv
#         (Poore & Nemecek 2018 via Our World in Data)
#         Median of 43 products = 1.6 kg CO2e / kg food  (verified from actual data)
# ──────────────────────────────────────────────────────────────────────────────
EMISSION_FACTOR_KG_CO2_PER_KG_FOOD: float = 1.6
"""
kg CO2e per kg of food avoided/redistributed.
ESTIMATED. Source: Median of Total_emissions across 43 food products,
Poore & Nemecek (2018), Food_Production.csv. Median = 1.6 kg CO2e/kg (verified).
"""

WATER_FACTOR_LITERS_PER_KG_FOOD: float = 417.1
"""
Liters of freshwater per kg of food avoided/redistributed.
ESTIMATED. Source: Median of 'Freshwater withdrawals per kilogram' column,
Poore & Nemecek (2018), Food_Production.csv. Median = 417.1 L/kg (38 products, verified).
"""

KG_FOOD_PER_MEAL: float = 0.5
"""
Average kg of food per meal (assumed 500 g portion).
Source: WHO / FSSAI institutional meal serving norms.
"""

CO2E_LABEL    = "ESTIMATED — kg CO2e (based on median emission factor)"
WATER_LABEL   = "ESTIMATED — liters freshwater (based on median water withdrawal factor)"
MEALS_LABEL   = "Derived from reported meals_count field; fallback uses 0.5 kg/meal assumption"

# ──────────────────────────────────────────────────────────────────────────────
# CSV helpers
# ──────────────────────────────────────────────────────────────────────────────

def _read_csv(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        return [row for row in reader]


def _safe_float(value: str, default: float = 0.0, clamp_negative: bool = True) -> float:
    try:
        v = float(str(value).strip())
        if clamp_negative and v < 0:
            return 0.0
        return v
    except (ValueError, TypeError):
        return default


def _parse_date(value: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Core metric calculation
# ──────────────────────────────────────────────────────────────────────────────

def calculate_metrics(
    activity_records: list[dict] | None = None,
    emission_factor: float = EMISSION_FACTOR_KG_CO2_PER_KG_FOOD,
    water_factor: float = WATER_FACTOR_LITERS_PER_KG_FOOD,
) -> dict[str, Any]:
    """
    Calculate sustainability metrics from activity records.

    Expected record fields (flexible naming):
        kitchen_id               — identifier for the kitchen
        date                     — ISO date YYYY-MM-DD
        food_redistributed_kg    — kg of food successfully redistributed
        food_waste_avoided_kg    — kg of food waste avoided
        meals_count              — number of meals delivered (optional)

    Parameters
    ----------
    activity_records : list of dicts or None
        If None, loaded from SUSTAINABILITY_LOG_PATH (then EXCHANGE_LOG_PATH).
    emission_factor : float
        kg CO2e per kg food. Configurable; default from dataset median.
    water_factor : float
        Liters per kg food. Configurable; default from dataset median.

    Returns
    -------
    dict with sustainability metrics. Environmental values labelled ESTIMATED.
    """
    if activity_records is None:
        activity_records = _read_csv(SUSTAINABILITY_LOG_PATH)
        if not activity_records:
            activity_records = _read_csv(EXCHANGE_LOG_PATH)

    if not activity_records:
        return {
            "status": "no_data",
            "total_food_redistributed_kg": 0.0,
            "total_food_waste_avoided_kg": 0.0,
            "total_meals_redistributed": 0,
            "estimated_co2e_avoided_kg": 0.0,
            "estimated_water_saved_liters": 0.0,
            "co2e_label": CO2E_LABEL,
            "water_label": WATER_LABEL,
            "emission_factor_used": emission_factor,
            "water_factor_used": water_factor,
            "records_processed": 0,
        }

    total_redistributed = 0.0
    total_waste_avoided = 0.0
    total_meals         = 0

    for row in activity_records:
        redistributed = _safe_float(
            row.get("food_redistributed_kg") or row.get("quantity_redistributed_kg") or
            row.get("quantity_kg") or "0"
        )
        waste_avoided = _safe_float(
            row.get("food_waste_avoided_kg") or row.get("waste_avoided_kg") or "0"
        )
        meals = int(_safe_float(
            row.get("meals_count") or row.get("meals") or "0"
        ))

        total_redistributed += redistributed
        total_waste_avoided += waste_avoided
        total_meals         += meals

    # If meals_count not in records, estimate from redistributed kg
    if total_meals == 0 and total_redistributed > 0:
        total_meals = int(total_redistributed / KG_FOOD_PER_MEAL)
        meals_source = "estimated_from_kg"
    else:
        meals_source = "from_records"

    # Environmental estimates — clearly labelled as ESTIMATED
    co2e_avoided    = round(total_waste_avoided * emission_factor, 4)
    water_saved     = round(total_waste_avoided * water_factor, 4)

    return {
        "status": "ok",
        "records_processed": len(activity_records),
        "total_food_redistributed_kg": round(total_redistributed, 4),
        "total_food_waste_avoided_kg": round(total_waste_avoided, 4),
        "total_meals_redistributed": total_meals,
        "meals_source": meals_source,
        "estimated_co2e_avoided_kg": co2e_avoided,
        "estimated_water_saved_liters": water_saved,
        "co2e_label": CO2E_LABEL,
        "water_label": WATER_LABEL,
        "emission_factor_used": emission_factor,
        "water_factor_used": water_factor,
        "emission_factor_source": (
            "Median of Total_emissions column, Food_Production.csv "
            "(Poore & Nemecek 2018 via Our World in Data)"
        ),
        "water_factor_source": (
            "Median of 'Freshwater withdrawals per kilogram', Food_Production.csv "
            "(Poore & Nemecek 2018 via Our World in Data)"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_by_date(
    activity_records: list[dict] | None = None,
    emission_factor: float = EMISSION_FACTOR_KG_CO2_PER_KG_FOOD,
    water_factor: float = WATER_FACTOR_LITERS_PER_KG_FOOD,
) -> list[dict[str, Any]]:
    """
    Return a list of daily aggregated metrics, sorted by date.
    Useful for sustainability trend analysis.
    """
    if activity_records is None:
        activity_records = _read_csv(SUSTAINABILITY_LOG_PATH)

    buckets: dict[str, dict] = defaultdict(lambda: {
        "food_redistributed_kg": 0.0,
        "food_waste_avoided_kg": 0.0,
        "meals_count": 0,
    })

    for row in activity_records:
        raw_date = (row.get("date") or row.get("activity_date") or "").strip()
        date_key = _parse_date(raw_date) or raw_date or "unknown"
        buckets[date_key]["food_redistributed_kg"] += _safe_float(
            row.get("food_redistributed_kg") or row.get("quantity_kg") or "0"
        )
        buckets[date_key]["food_waste_avoided_kg"] += _safe_float(
            row.get("food_waste_avoided_kg") or "0"
        )
        buckets[date_key]["meals_count"] += int(_safe_float(
            row.get("meals_count") or row.get("meals") or "0"
        ))

    result = []
    for date_key, vals in sorted(buckets.items()):
        waste_avoided = vals["food_waste_avoided_kg"]
        result.append({
            "date":                       date_key,
            "food_redistributed_kg":      round(vals["food_redistributed_kg"], 4),
            "food_waste_avoided_kg":      round(waste_avoided, 4),
            "meals_count":                vals["meals_count"],
            "estimated_co2e_avoided_kg":  round(waste_avoided * emission_factor, 4),
            "estimated_water_saved_liters": round(waste_avoided * water_factor, 4),
        })
    return result


def aggregate_by_kitchen(
    activity_records: list[dict] | None = None,
    emission_factor: float = EMISSION_FACTOR_KG_CO2_PER_KG_FOOD,
    water_factor: float = WATER_FACTOR_LITERS_PER_KG_FOOD,
) -> list[dict[str, Any]]:
    """
    Return per-kitchen aggregated metrics, sorted by kitchen_id.
    """
    if activity_records is None:
        activity_records = _read_csv(SUSTAINABILITY_LOG_PATH)

    buckets: dict[str, dict] = defaultdict(lambda: {
        "food_redistributed_kg": 0.0,
        "food_waste_avoided_kg": 0.0,
        "meals_count": 0,
        "record_count": 0,
    })

    for row in activity_records:
        kitchen = (row.get("kitchen_id") or row.get("kitchen") or "unknown").strip()
        buckets[kitchen]["food_redistributed_kg"] += _safe_float(
            row.get("food_redistributed_kg") or row.get("quantity_kg") or "0"
        )
        buckets[kitchen]["food_waste_avoided_kg"] += _safe_float(
            row.get("food_waste_avoided_kg") or "0"
        )
        buckets[kitchen]["meals_count"] += int(_safe_float(
            row.get("meals_count") or row.get("meals") or "0"
        ))
        buckets[kitchen]["record_count"] += 1

    result = []
    for kitchen_id, vals in sorted(buckets.items()):
        waste_avoided = vals["food_waste_avoided_kg"]
        result.append({
            "kitchen_id":                   kitchen_id,
            "food_redistributed_kg":        round(vals["food_redistributed_kg"], 4),
            "food_waste_avoided_kg":        round(waste_avoided, 4),
            "meals_count":                  vals["meals_count"],
            "record_count":                 vals["record_count"],
            "estimated_co2e_avoided_kg":    round(waste_avoided * emission_factor, 4),
            "estimated_water_saved_liters": round(waste_avoided * water_factor, 4),
        })
    return result


def get_sustainability_trend(
    activity_records: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Returns trend data: overall direction and per-date time series.
    """
    daily = aggregate_by_date(activity_records)
    if len(daily) < 2:
        return {
            "trend": "insufficient_data",
            "daily_series": daily,
            "message": "At least 2 data points are required for trend analysis.",
        }

    # Simple linear trend: compare first half avg vs second half avg
    mid = len(daily) // 2
    first_half  = [d["food_redistributed_kg"] for d in daily[:mid]]
    second_half = [d["food_redistributed_kg"] for d in daily[mid:]]
    avg_first  = sum(first_half) / len(first_half)   if first_half  else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0

    if avg_second > avg_first * 1.05:
        trend = "improving"
    elif avg_second < avg_first * 0.95:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "trend": trend,
        "avg_redistributed_first_half_kg": round(avg_first, 4),
        "avg_redistributed_second_half_kg": round(avg_second, 4),
        "daily_series": daily,
    }
