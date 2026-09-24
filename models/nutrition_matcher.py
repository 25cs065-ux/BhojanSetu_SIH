"""
models/nutrition_matcher.py
============================
Feature 5 — Nutrition-Aware Matching for BhojanSetu.

PURPOSE
-------
Enhance NGO/recipient matching by considering the nutritional content of
surplus food.  This module works ON TOP OF the normal NGO matching system
(models/matching_engine.py).  It does NOT duplicate the base matching logic.

DATASETS USED (READ-ONLY)
--------------------------
Primary:
    datasets/Indian_Food_Nutrition_Processed.csv
        Columns: Dish Name, Calories (kcal), Carbohydrates (g), Protein (g),
                 Fats (g), Free Sugar (g), Fibre (g), Sodium (mg),
                 Calcium (mg), Iron (mg), Vitamin C (mg), Folate (μg)

Secondary (combined, identical schema GROUP1–GROUP5):
    datasets/FOOD-DATA-GROUP1.csv  …  datasets/FOOD-DATA-GROUP5.csv
        Key columns: food, Caloric Value, Protein, Fat, Dietary Fiber,
                     Carbohydrates, Calcium, Iron, Vitamin C

Search order: Indian_Food_Nutrition_Processed first (more India-relevant),
              then GROUP datasets if not found.

Matching strategy
-----------------
1. Normalise the food item name (lower-case, strip).
2. Try exact match → partial (substring) match in dataset.
3. If found: extract nutrition profile and compute nutrition_score.
4. If NOT found: return no_nutrition_data=True and use score=0.5 (neutral).

Nutrition profile keys returned
---------------------------------
    calories_kcal, protein_g, carbs_g, fats_g, fibre_g, calcium_mg, iron_mg

Recipient nutrition profile (optional)
---------------------------------------
NGOs may have a 'nutrition_priority' field in their record, e.g.:
    {"nutrition_priority": "protein"}  or  {"nutrition_priority": "iron"}

If a nutrition_priority is present, the nutrition_score is boosted when the
food item is rich in that nutrient.

INTEGRATION INTERFACE
---------------------
Key dataclasses / types
    NutritionProfile        – nutrition values for one food item
    NutritionMatchResult    – enriched NGOMatchResult with nutrition info

Key functions
    load_nutrition_db() -> NutritionDB
        Load and cache the nutrition dataset once.  Returns a NutritionDB
        helper object.  Call once at startup.

    get_nutrition_profile(food_name, db) -> NutritionProfile | None
        Look up a food item.  Returns None if not found in any dataset.

    nutrition_score(profile, priority) -> float
        Score [0,1] – how well a food's nutrition matches a priority.
        Returns 0.5 (neutral) if priority is None or profile has no data.

    enrich_matches(surplus_food_item, ngo_matches, db,
                   nutrition_weight=0.15) -> list[NutritionMatchResult]
        Take the output of match_ngos() and re-rank adding a nutrition
        component.  nutrition_weight is the fraction of the final score
        attributed to nutrition (applied on top of the existing score).

Public constants
    NUTRITION_PRIORITIES  – set of recognised priority keywords
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.matching_engine import NGOMatchResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATASETS_DIR = os.path.join(_HERE, "..", "datasets")

_INDIAN_NUTRITION_PATH = os.path.join(
    _DATASETS_DIR, "Indian_Food_Nutrition_Processed.csv"
)
_GROUP_PATHS = [
    os.path.join(_DATASETS_DIR, f"FOOD-DATA-GROUP{i}.csv") for i in range(1, 6)
]

# Nutrients considered "high" when they exceed these per-100g thresholds
_HIGH_PROTEIN_G = 10.0
_HIGH_IRON_MG = 2.0
_HIGH_CALCIUM_MG = 100.0
_HIGH_FIBRE_G = 5.0
_HIGH_VITAMIN_C_MG = 20.0
_HIGH_CALORIE_KCAL = 300.0

NUTRITION_PRIORITIES = frozenset(
    {"protein", "iron", "calcium", "fibre", "vitamin_c", "calories", "energy"}
)

# Weight applied ON TOP of the base matching score
_DEFAULT_NUTRITION_WEIGHT = 0.15


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NutritionProfile:
    """Nutritional attributes for one food item (per 100 g / per serving).

    Fields that cannot be extracted from the dataset are set to None.

    Fields
    ------
    food_name     : str            – normalised food name
    source        : str            – 'indian' | 'group' | 'unknown'
    calories_kcal : float | None
    protein_g     : float | None
    carbs_g       : float | None
    fats_g        : float | None
    fibre_g       : float | None
    calcium_mg    : float | None
    iron_mg       : float | None
    vitamin_c_mg  : float | None
    no_data       : bool           – True when food was not found in any dataset
    """

    food_name: str
    source: str = "unknown"
    calories_kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fats_g: Optional[float] = None
    fibre_g: Optional[float] = None
    calcium_mg: Optional[float] = None
    iron_mg: Optional[float] = None
    vitamin_c_mg: Optional[float] = None
    no_data: bool = False

    def to_dict(self) -> dict:
        return {
            "food_name": self.food_name,
            "source": self.source,
            "calories_kcal": self.calories_kcal,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fats_g": self.fats_g,
            "fibre_g": self.fibre_g,
            "calcium_mg": self.calcium_mg,
            "iron_mg": self.iron_mg,
            "vitamin_c_mg": self.vitamin_c_mg,
            "no_data": self.no_data,
        }


@dataclass
class NutritionMatchResult:
    """An NGO match result enriched with nutrition information.

    Fields
    ------
    base_match          : NGOMatchResult  – original match from matching_engine
    nutrition_profile   : NutritionProfile | None
    nutrition_score     : float           – [0,1]; 0.5 if no nutrition data
    adjusted_score      : float           – base score re-weighted with nutrition
    nutrition_priority  : str | None      – NGO's stated nutrition priority
    nutrition_reason    : str             – explanation of nutrition influence
    """

    base_match: NGOMatchResult
    nutrition_profile: Optional[NutritionProfile]
    nutrition_score: float
    adjusted_score: float
    nutrition_priority: Optional[str]
    nutrition_reason: str

    def to_dict(self) -> dict:
        d = self.base_match.to_dict()
        d.update(
            {
                "nutrition_score": self.nutrition_score,
                "adjusted_score": self.adjusted_score,
                "nutrition_priority": self.nutrition_priority,
                "nutrition_reason": self.nutrition_reason,
                "nutrition_profile": (
                    self.nutrition_profile.to_dict()
                    if self.nutrition_profile
                    else None
                ),
            }
        )
        return d


# ---------------------------------------------------------------------------
# NutritionDB – in-memory lookup cache
# ---------------------------------------------------------------------------


class NutritionDB:
    """In-memory nutrition lookup built from the available datasets.

    Build once with NutritionDB.build() and reuse.
    """

    def __init__(
        self,
        indian_index: Dict[str, NutritionProfile],
        group_index: Dict[str, NutritionProfile],
    ) -> None:
        self._indian = indian_index
        self._group = group_index

    @classmethod
    def build(cls) -> "NutritionDB":
        """Load the nutrition datasets and build lookup indices."""
        indian = _load_indian_nutrition()
        group = _load_group_nutrition()
        return cls(indian, group)

    def lookup(self, food_name: str) -> Optional[NutritionProfile]:
        """Return NutritionProfile for food_name, or None if not found.

        Search order: Indian dataset first, then GROUP datasets.
        Uses exact (normalised) match first, then substring.
        """
        key = food_name.strip().lower()
        # 1. exact match in Indian dataset
        if key in self._indian:
            return self._indian[key]
        # 2. exact match in GROUP datasets
        if key in self._group:
            return self._group[key]
        # 3. substring match in Indian dataset
        for k, profile in self._indian.items():
            if key in k or k in key:
                return profile
        # 4. substring match in GROUP datasets
        for k, profile in self._group.items():
            if key in k or k in key:
                return profile
        return None

    def size(self) -> int:
        return len(self._indian) + len(self._group)


# ---------------------------------------------------------------------------
# Dataset loaders (READ-ONLY, never write back)
# ---------------------------------------------------------------------------


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(str(value).strip())
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


def _load_indian_nutrition() -> Dict[str, NutritionProfile]:
    """Load Indian_Food_Nutrition_Processed.csv into a name→profile dict."""
    index: Dict[str, NutritionProfile] = {}
    if not os.path.exists(_INDIAN_NUTRITION_PATH):
        return index
    with open(_INDIAN_NUTRITION_PATH, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name_raw = row.get("Dish Name", "").strip()
            if not name_raw:
                continue
            key = name_raw.lower()
            profile = NutritionProfile(
                food_name=name_raw,
                source="indian",
                calories_kcal=_safe_float(row.get("Calories (kcal)")),
                protein_g=_safe_float(row.get("Protein (g)")),
                carbs_g=_safe_float(row.get("Carbohydrates (g)")),
                fats_g=_safe_float(row.get("Fats (g)")),
                fibre_g=_safe_float(row.get("Fibre (g)")),
                calcium_mg=_safe_float(row.get("Calcium (mg)")),
                iron_mg=_safe_float(row.get("Iron (mg)")),
                vitamin_c_mg=_safe_float(row.get("Vitamin C (mg)")),
            )
            index[key] = profile
    return index


def _load_group_nutrition() -> Dict[str, NutritionProfile]:
    """Load FOOD-DATA-GROUP1–5.csv (identical schema) into a name→profile dict."""
    index: Dict[str, NutritionProfile] = {}
    for path in _GROUP_PATHS:
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name_raw = row.get("food", "").strip()
                if not name_raw:
                    continue
                key = name_raw.lower()
                if key in index:
                    continue  # first file wins
                profile = NutritionProfile(
                    food_name=name_raw,
                    source="group",
                    calories_kcal=_safe_float(row.get("Caloric Value")),
                    protein_g=_safe_float(row.get("Protein")),
                    carbs_g=_safe_float(row.get("Carbohydrates")),
                    fats_g=_safe_float(row.get("Fat")),
                    fibre_g=_safe_float(row.get("Dietary Fiber")),
                    calcium_mg=_safe_float(row.get("Calcium")),
                    iron_mg=_safe_float(row.get("Iron")),
                    vitamin_c_mg=_safe_float(row.get("Vitamin C")),
                )
                index[key] = profile
    return index


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Module-level cache so callers can call load_nutrition_db() multiple times cheaply
_DB_CACHE: Optional[NutritionDB] = None


def load_nutrition_db() -> NutritionDB:
    """Load (or return cached) NutritionDB from the available datasets.

    Returns
    -------
    NutritionDB – call .lookup(food_name) to query it
    """
    global _DB_CACHE
    if _DB_CACHE is None:
        _DB_CACHE = NutritionDB.build()
    return _DB_CACHE


def get_nutrition_profile(
    food_name: str, db: NutritionDB
) -> Optional[NutritionProfile]:
    """Look up a food item in the nutrition database.

    Parameters
    ----------
    food_name : str       – name of the food item to look up
    db        : NutritionDB – built with load_nutrition_db()

    Returns
    -------
    NutritionProfile if found, None otherwise.
    Never fabricates nutrition data.
    """
    if not food_name or not food_name.strip():
        return None
    return db.lookup(food_name)


def nutrition_score(
    profile: Optional[NutritionProfile],
    priority: Optional[str],
) -> float:
    """Compute a nutrition compatibility score [0, 1].

    Parameters
    ----------
    profile  : NutritionProfile | None  – food's nutrition data (may be None)
    priority : str | None               – NGO's stated nutrition priority, e.g.
                                          'protein', 'iron', 'calcium', etc.
                                          None means no specific preference.

    Returns
    -------
    float in [0, 1]:
        0.5  – if no nutrition data or no priority (neutral)
        1.0  – food is rich in the priority nutrient
        0.7  – food has moderate amounts of the priority nutrient
        0.3  – food is low in the priority nutrient
    """
    if profile is None or profile.no_data:
        return 0.5  # neutral: no data, cannot penalise or reward
    if priority is None:
        return 0.5  # no preference stated

    prio = priority.strip().lower()

    # Map priority keyword → (profile_attribute, high_threshold)
    nutrient_map = {
        "protein": (profile.protein_g, _HIGH_PROTEIN_G),
        "iron": (profile.iron_mg, _HIGH_IRON_MG),
        "calcium": (profile.calcium_mg, _HIGH_CALCIUM_MG),
        "fibre": (profile.fibre_g, _HIGH_FIBRE_G),
        "fiber": (profile.fibre_g, _HIGH_FIBRE_G),
        "vitamin_c": (profile.vitamin_c_mg, _HIGH_VITAMIN_C_MG),
        "calories": (profile.calories_kcal, _HIGH_CALORIE_KCAL),
        "energy": (profile.calories_kcal, _HIGH_CALORIE_KCAL),
    }

    if prio not in nutrient_map:
        return 0.5  # unrecognised priority → neutral

    value, threshold = nutrient_map[prio]
    if value is None:
        return 0.5  # nutrient not in dataset → neutral

    if value >= threshold:
        return 1.0
    if value >= threshold * 0.4:
        return 0.7
    return 0.3


def enrich_matches(
    surplus_food_item: str,
    ngo_matches: List[NGOMatchResult],
    db: NutritionDB,
    nutrition_weight: float = _DEFAULT_NUTRITION_WEIGHT,
) -> List[NutritionMatchResult]:
    """Enrich base NGO matches with nutrition information and re-rank.

    This function takes the output of match_ngos() and:
    1. Looks up the nutrition profile of the surplus food item.
    2. For each NGO match, computes a nutrition compatibility score based on
       the NGO's nutrition_priority (if any).
    3. Computes an adjusted_score = base_score * (1 - w) + nutrition_score * w
       where w = nutrition_weight.
    4. Re-sorts by adjusted_score descending.

    Parameters
    ----------
    surplus_food_item : str              – name of the surplus food
    ngo_matches       : list[NGOMatchResult] – output of match_ngos()
    db                : NutritionDB      – loaded with load_nutrition_db()
    nutrition_weight  : float            – fraction of final score from nutrition
                                          (default 0.15)

    Returns
    -------
    list[NutritionMatchResult] sorted by adjusted_score descending.
    Falls back gracefully when nutrition data is unavailable.
    """
    profile = get_nutrition_profile(surplus_food_item, db)

    enriched: List[NutritionMatchResult] = []
    for base in ngo_matches:
        prio = _get_ngo_priority(base.ngo)
        nut_sc = nutrition_score(profile, prio)
        adjusted = base.score * (1.0 - nutrition_weight) + nut_sc * nutrition_weight
        reason = _build_nutrition_reason(profile, prio, nut_sc, surplus_food_item)

        enriched.append(
            NutritionMatchResult(
                base_match=base,
                nutrition_profile=profile,
                nutrition_score=round(nut_sc, 4),
                adjusted_score=round(adjusted, 4),
                nutrition_priority=prio,
                nutrition_reason=reason,
            )
        )

    enriched.sort(key=lambda r: r.adjusted_score, reverse=True)
    return enriched


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_ngo_priority(ngo) -> Optional[str]:
    """Extract nutrition_priority from an NGORecord if present.

    NGORecord objects may or may not have a nutrition_priority attribute
    (it comes from optional JSON data).  This helper avoids AttributeError.
    """
    raw = getattr(ngo, "nutrition_priority", None)
    if raw is None:
        # Also check if it was stored as part of raw dict attributes
        return None
    val = str(raw).strip().lower()
    return val if val else None


def _build_nutrition_reason(
    profile: Optional[NutritionProfile],
    priority: Optional[str],
    score: float,
    food_name: str,
) -> str:
    if profile is None:
        return (
            f"No nutrition data found for '{food_name}' in the database. "
            "Base matching score used without nutrition adjustment."
        )
    if priority is None:
        return (
            f"Nutrition data available for '{food_name}' "
            f"(protein={profile.protein_g}g, calories={profile.calories_kcal}kcal) "
            "but no NGO nutrition priority specified — neutral score applied."
        )
    prio_label = priority.replace("_", " ")
    if score >= 0.9:
        return (
            f"'{food_name}' is rich in {prio_label} "
            f"— matches NGO's stated priority. Strong nutrition compatibility."
        )
    if score >= 0.6:
        return (
            f"'{food_name}' has moderate {prio_label} content "
            f"— partially matches NGO's nutrition priority."
        )
    return (
        f"'{food_name}' is low in {prio_label} "
        f"— limited match with NGO's nutrition priority."
    )
