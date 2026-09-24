"""
Production Planner — Feature 7
Data-driven production planning recommendations derived from historical
surplus, raw-material, exchange, and production-plan records.

All recommendations cite actual calculated evidence; nothing is invented.
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, date
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Paths (relative to project root)
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

SURPLUS_LOG_PATH      = os.path.join(DATA_DIR, "surplus_log.csv")
RAW_MATERIAL_LOG_PATH = os.path.join(DATA_DIR, "raw_material_log.csv")
EXCHANGE_LOG_PATH     = os.path.join(DATA_DIR, "exchange_log.csv")
PRODUCTION_PLAN_PATH  = os.path.join(DATA_DIR, "production_plan.csv")

# ──────────────────────────────────────────────────────────────────────────────
# Confidence thresholds (fraction of records showing the pattern)
# ──────────────────────────────────────────────────────────────────────────────
CONFIDENCE_HIGH   = 0.60   # ≥ 60 % of records
CONFIDENCE_MEDIUM = 0.35   # 35–60 %
CONFIDENCE_LOW    = 0.10   # 10–35 %


# ──────────────────────────────────────────────────────────────────────────────
# CSV helpers
# ──────────────────────────────────────────────────────────────────────────────

def _read_csv(path: str) -> list[dict[str, str]]:
    """Read a CSV file; return [] if missing or empty."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        return [row for row in reader]


def _parse_date(value: str) -> date | None:
    """Try several common date formats; return None on failure."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Core analysis
# ──────────────────────────────────────────────────────────────────────────────

def _analyse_surplus(records: list[dict]) -> dict[str, dict]:
    """
    Count how many records show surplus per item.
    Expected CSV fields: item_name, quantity_kg, date, kitchen_id  (flexible)
    """
    counts: dict[str, int] = defaultdict(int)
    dates:  dict[str, list[date]] = defaultdict(list)

    for row in records:
        # Support multiple possible field name styles
        item = (
            row.get("item_name") or row.get("item") or
            row.get("food_item") or row.get("ingredient") or ""
        ).strip()
        if not item:
            continue

        qty_str = (
            row.get("surplus_quantity_kg") or row.get("quantity_kg") or
            row.get("quantity") or row.get("surplus_kg") or "0"
        ).strip()

        try:
            qty = float(qty_str)
        except ValueError:
            qty = 0.0

        dt_str = (
            row.get("date") or row.get("surplus_date") or row.get("timestamp") or ""
        ).strip()
        dt = _parse_date(dt_str)

        if qty > 0:
            counts[item] += 1
            if dt:
                dates[item].append(dt)

    total = len(records) if records else 1
    return {
        item: {
            "surplus_occurrences": counts[item],
            "total_records": total,
            "fraction": counts[item] / total,
            "date_range": (
                (min(dates[item]).isoformat(), max(dates[item]).isoformat())
                if dates[item] else (None, None)
            ),
        }
        for item in counts
    }


def _analyse_raw_material(records: list[dict]) -> dict[str, dict]:
    """
    Count procurement events per item.
    Expected fields: item_name, quantity_kg, date
    """
    counts: dict[str, int] = defaultdict(int)
    total_qty: dict[str, float] = defaultdict(float)

    for row in records:
        item = (
            row.get("item_name") or row.get("item") or row.get("ingredient") or ""
        ).strip()
        if not item:
            continue
        qty_str = (row.get("quantity_kg") or row.get("quantity") or "0").strip()
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 0.0
        counts[item] += 1
        total_qty[item] += qty

    return {
        item: {
            "procurement_count": counts[item],
            "total_procured_kg": round(total_qty[item], 3),
        }
        for item in counts
    }


# ──────────────────────────────────────────────────────────────────────────────
# Recommendation builder
# ──────────────────────────────────────────────────────────────────────────────

def _confidence_label(fraction: float) -> str:
    if fraction >= CONFIDENCE_HIGH:
        return "HIGH"
    if fraction >= CONFIDENCE_MEDIUM:
        return "MEDIUM"
    if fraction >= CONFIDENCE_LOW:
        return "LOW"
    return "WEAK"


def _build_recommendation(
    item: str,
    surplus_info: dict,
    raw_info: dict | None,
) -> dict[str, Any]:
    frac = surplus_info["fraction"]
    n    = surplus_info["surplus_occurrences"]
    m    = surplus_info["total_records"]
    dr   = surplus_info["date_range"]
    conf = _confidence_label(frac)

    date_range_str = (
        f"{dr[0]} to {dr[1]}" if dr[0] and dr[1]
        else "date range unavailable"
    )

    rec: dict[str, Any] = {
        "item": item,
        "recommendation": f"Recommendation: reduce future procurement/preparation of '{item}'.",
        "reason": (
            f"This ingredient appears as surplus in {n} of {m} available records "
            f"({frac:.0%} of all surplus events)."
        ),
        "evidence": {
            "surplus_occurrences": n,
            "total_surplus_records_analysed": m,
            "fraction_of_records": round(frac, 4),
            "date_range": date_range_str,
        },
        "confidence": conf,
    }

    if raw_info:
        rec["evidence"]["total_procured_kg"] = raw_info["total_procured_kg"]
        rec["evidence"]["procurement_events"] = raw_info["procurement_count"]

    return rec


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_recommendations(
    surplus_records: list[dict] | None = None,
    raw_material_records: list[dict] | None = None,
    min_occurrences: int = 2,
    min_fraction: float = CONFIDENCE_LOW,
) -> dict[str, Any]:
    """
    Analyse historical records and return production planning recommendations.

    Parameters
    ----------
    surplus_records : list of dicts (optional)
        If None, loaded from SURPLUS_LOG_PATH.
    raw_material_records : list of dicts (optional)
        If None, loaded from RAW_MATERIAL_LOG_PATH.
    min_occurrences : int
        Minimum surplus events for an item to generate a recommendation.
    min_fraction : float
        Minimum fraction of records for inclusion (default 10 %).

    Returns
    -------
    dict with keys:
        records_analysed, recommendations, metadata
    """
    if surplus_records is None:
        surplus_records = _read_csv(SURPLUS_LOG_PATH)
    if raw_material_records is None:
        raw_material_records = _read_csv(RAW_MATERIAL_LOG_PATH)

    if not surplus_records:
        return {
            "records_analysed": 0,
            "recommendations": [],
            "metadata": {
                "status": "no_data",
                "message": "No surplus records available for analysis.",
            },
        }

    surplus_analysis   = _analyse_surplus(surplus_records)
    raw_material_index = _analyse_raw_material(raw_material_records)

    recommendations = []
    for item, info in sorted(surplus_analysis.items(), key=lambda x: -x[1]["fraction"]):
        if info["surplus_occurrences"] < min_occurrences:
            continue
        if info["fraction"] < min_fraction:
            continue
        rec = _build_recommendation(
            item=item,
            surplus_info=info,
            raw_info=raw_material_index.get(item),
        )
        recommendations.append(rec)

    all_items = sorted(surplus_analysis.keys())
    return {
        "records_analysed": len(surplus_records),
        "recommendations": recommendations,
        "metadata": {
            "status": "ok",
            "total_items_in_surplus": len(all_items),
            "items_with_recommendations": len(recommendations),
            "surplus_items_observed": all_items,
            "thresholds": {
                "min_occurrences": min_occurrences,
                "min_fraction": min_fraction,
            },
        },
    }


def get_item_history(item_name: str, surplus_records: list[dict] | None = None) -> dict:
    """Return detailed surplus history for a single item."""
    if surplus_records is None:
        surplus_records = _read_csv(SURPLUS_LOG_PATH)

    if not surplus_records:
        return {"item": item_name, "records": [], "summary": "No data available."}

    item_records = [
        r for r in surplus_records
        if (r.get("item_name") or r.get("item") or r.get("food_item") or "").strip()
        == item_name.strip()
    ]
    return {
        "item": item_name,
        "matching_records": len(item_records),
        "records": item_records,
        "summary": (
            f"{len(item_records)} surplus record(s) found for '{item_name}' "
            f"out of {len(surplus_records)} total records."
        ),
    }
