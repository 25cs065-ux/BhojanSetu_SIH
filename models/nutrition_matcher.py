"""
models/nutrition_matcher.py
----------------------------
Enhances a match list by looking up nutritional data for the surplus food
item and computing a nutrition score that can adjust the final NGO ranking.

Data source
-----------
datasets/Indian_Food_Nutrition_Processed.csv
Columns: Dish Name, Calories (kcal), Carbohydrates (g), Protein (g),
         Fats (g), Free Sugar (g), Fibre (g), Sodium (mg), Calcium (mg),
         Iron (mg), Vitamin C (mg), Folate (µg)

Lookup strategy
---------------
1. Exact case-insensitive match on "Dish Name".
2. If no exact match: find the first row whose dish name contains any word
   from the query (length >= 4), take the first hit.
3. If still no match: return None for nutrition data.

Nutrition score
---------------
A simple Protein-Fibre-Vitamin C composite score per 100 g:
   nutrition_score = (Protein_g * 4) + (Fibre_g * 2) + (Vitamin_C_mg * 0.1)

The three factors are chosen because they represent commonly deficient
nutrients in populations served by food-relief NGOs.

Ranking boost
-------------
Each match entry in the list gets an optional nutrition_boost (0–10):
   boost = min(nutrition_score / 10, 1.0) * 10

adjusted_score = original_score + nutrition_boost

Matches are re-sorted by adjusted_score descending when nutrition data
is available. If nutrition data is unavailable the original order is
preserved and a warning is added.

Assumptions
-----------
- This is NOT a medical nutrition decision. Scores are informational only.
- All nutritional values are per-100 g as provided in the dataset.
- No values are fabricated; all come directly from the CSV file.
"""

from __future__ import annotations

import csv
import os
from typing import Any

_DATASET_PATH = os.path.join(
    os.path.dirname(__file__), "..", "datasets",
    "Indian_Food_Nutrition_Processed.csv"
)

# Nutrition score weights – purely informational
_W_PROTEIN = 4.0      # g protein per 100 g
_W_FIBRE = 2.0        # g fibre per 100 g
_W_VITAMIN_C = 0.1    # mg vitamin C per 100 g

_NUTRITION_BOOST_MAX = 10.0


def _load_nutrition_index(dataset_path: str | None = None) -> dict[str, dict]:
    """
    Load the Indian food nutrition CSV into a dict keyed by lowercased
    dish name.  Returns {} if the file cannot be read.
    """
    path = dataset_path or _DATASET_PATH
    index: dict[str, dict] = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Dish Name", "").strip()
                if name:
                    index[name.lower()] = row
    except OSError as exc:
        # File missing; caller will handle via returned empty dict
        pass
    return index


def lookup_nutrition(
    food_name: str,
    dataset_path: str | None = None,
) -> dict[str, Any] | None:
    """
    Look up nutritional data for food_name from the Indian nutrition CSV.

    Returns a dict with keys from the CSV header on success, or None if
    no match is found or the dataset is unavailable.
    """
    index = _load_nutrition_index(dataset_path)
    if not index:
        return None

    query = food_name.strip().lower()

    # 1. Exact match
    if query in index:
        return index[query]

    # 2. Substring match: query is a substring of a dish name
    for key, row in index.items():
        if query in key:
            return row

    # 3. Word overlap match (words >= 4 chars)
    query_words = [w for w in query.split() if len(w) >= 4]
    for key, row in index.items():
        for word in query_words:
            if word in key:
                return row

    return None


def _nutrition_score(row: dict) -> float:
    """
    Compute a simple nutrition composite score from a CSV row.
    Returns 0.0 if fields are missing or non-numeric.
    """
    def _f(col: str) -> float:
        try:
            return float(row.get(col, 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    protein = _f("Protein (g)")
    fibre = _f("Fibre (g)")
    vitamin_c = _f("Vitamin C (mg)")
    return protein * _W_PROTEIN + fibre * _W_FIBRE + vitamin_c * _W_VITAMIN_C


def enhance_matches(
    match_result: dict[str, Any],
    dataset_path: str | None = None,
) -> dict[str, Any]:
    """
    Enhance a match_result dict (as returned by matching_engine.match_surplus)
    with nutritional information and re-rank matches by adjusted_score.

    Parameters
    ----------
    match_result : dict returned by match_surplus()
    dataset_path : override path to nutrition CSV (for testing)

    Returns
    -------
    Same dict structure, with each match entry enriched:
        nutrition_data     – raw dict from CSV, or None
        nutrition_score    – composite score (float)
        nutrition_boost    – 0–10 additive ranking bonus
        adjusted_score     – score + nutrition_boost
    Matches re-sorted by adjusted_score descending (nutrition-aware).
    A new key "nutrition_lookup" is added at top level:
        food_name_queried  – the food_name used for lookup
        dish_matched       – dish name from CSV that was matched, or None
        lookup_status      – "exact" | "partial" | "not_found" | "unavailable"
    """
    food_name = match_result.get("food_name", "")
    warnings: list[str] = list(match_result.get("warnings", []))

    index = _load_nutrition_index(dataset_path)

    if not index:
        for m in match_result.get("matches", []):
            m["nutrition_data"] = None
            m["nutrition_score"] = 0.0
            m["nutrition_boost"] = 0.0
            m["adjusted_score"] = m["score"]
        match_result["nutrition_lookup"] = {
            "food_name_queried": food_name,
            "dish_matched": None,
            "lookup_status": "unavailable",
        }
        warnings.append("Nutrition dataset unavailable; no boost applied.")
        match_result["warnings"] = warnings
        return match_result

    # Resolve the nutrition row
    query = food_name.strip().lower()
    lookup_status = "not_found"
    matched_dish = None
    nutrition_row = None

    if query in index:
        nutrition_row = index[query]
        matched_dish = nutrition_row["Dish Name"]
        lookup_status = "exact"
    else:
        # substring or word overlap
        for key, row in index.items():
            if query in key or key in query:
                nutrition_row = row
                matched_dish = row["Dish Name"]
                lookup_status = "partial"
                break
        if nutrition_row is None:
            query_words = [w for w in query.split() if len(w) >= 4]
            for key, row in index.items():
                for word in query_words:
                    if word in key:
                        nutrition_row = row
                        matched_dish = row["Dish Name"]
                        lookup_status = "partial"
                        break
                if nutrition_row:
                    break

    if nutrition_row is None:
        n_score = 0.0
        n_boost = 0.0
        warnings.append(
            f"No nutrition data found for '{food_name}'; boost not applied."
        )
    else:
        n_score = round(_nutrition_score(nutrition_row), 4)
        n_boost = round(min(n_score / 10.0, 1.0) * _NUTRITION_BOOST_MAX, 4)

    for m in match_result.get("matches", []):
        m["nutrition_data"] = nutrition_row
        m["nutrition_score"] = n_score
        m["nutrition_boost"] = n_boost
        m["adjusted_score"] = round(m["score"] + n_boost, 2)

    # Re-sort by adjusted_score
    match_result["matches"].sort(
        key=lambda m: m["adjusted_score"], reverse=True
    )

    match_result["nutrition_lookup"] = {
        "food_name_queried": food_name,
        "dish_matched": matched_dish,
        "lookup_status": lookup_status,
    }
    match_result["warnings"] = warnings
    return match_result
