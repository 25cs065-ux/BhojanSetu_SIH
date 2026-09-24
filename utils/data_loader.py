"""
Data-loading utilities for the BhojanSetu project.

All functions read from the project's data/ directory.  Paths are resolved
relative to this file so the module works regardless of the caller's CWD.

Public API
----------
load_kitchens()         -> dict[str, dict]
    Returns a mapping of kitchen_id -> kitchen record dict.
    Returns {} if the file is empty or missing.

load_ngos()             -> list[dict]
    Returns a list of NGO/recipient records.
    Returns [] if the file is empty or missing.

load_surplus_log()      -> list[dict]
    Returns a list of surplus-log rows.
    Returns [] if the file is empty or missing.

load_matches()          -> list[dict]
    Returns a list of match records from matches.csv.
    Returns [] if the file is empty or missing.

load_raw_material_log() -> list[dict]
    Returns a list of raw-material listing rows (dicts).
    Returns [] if the file is empty or missing.

load_exchange_log()     -> list[dict]
    Returns a list of exchange record rows (dicts).
    Returns [] if the file is empty or missing.

save_raw_material_log(rows)
    Writes the supplied list[dict] back to raw_material_log.csv.

save_exchange_log(rows)
    Writes the supplied list[dict] back to exchange_log.csv.

save_matches(rows)
    Writes the supplied list[dict] back to matches.csv.

save_surplus_log(rows)
    Writes the supplied list[dict] back to surplus_log.csv.
"""

import csv
import json
import os
from typing import Dict, List

# ---------------------------------------------------------------------------
# Resolve absolute paths relative to this file so CWD never matters.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "..", "data")

_KITCHENS_PATH = os.path.join(_DATA_DIR, "kitchens.json")
_NGOS_PATH = os.path.join(_DATA_DIR, "ngos.json")
_SURPLUS_LOG_PATH = os.path.join(_DATA_DIR, "surplus_log.csv")
_MATCHES_PATH = os.path.join(_DATA_DIR, "matches.csv")
_RAW_MATERIAL_LOG_PATH = os.path.join(_DATA_DIR, "raw_material_log.csv")
_EXCHANGE_LOG_PATH = os.path.join(_DATA_DIR, "exchange_log.csv")

# Column schemas for CSV writers
_SURPLUS_COLUMNS = [
    "surplus_id",
    "kitchen_id",
    "food_item",
    "quantity_kg",
    "date_of_surplus",
    "expiry_time_hours",
    "urgency",
    "status",
]

_MATCHES_COLUMNS = [
    "match_id",
    "surplus_id",
    "kitchen_id",
    "ngo_id",
    "food_item",
    "quantity_kg",
    "distance_km",
    "score",
    "status",
    "created_at",
]

# Column order used when writing CSV files (mirrors RawMaterialListing /
# ExchangeProposal fields).
_RAW_MATERIAL_COLUMNS = [
    "listing_id",
    "kitchen_id",
    "ingredient",
    "quantity",
    "unit",
    "date_listed",
    "use_by_date",
    "status",
]

_EXCHANGE_COLUMNS = [
    "exchange_id",
    "listing_id",
    "offering_kitchen_id",
    "requesting_kitchen_id",
    "ingredient",
    "offered_quantity",
    "requested_quantity",
    "unit",
    "status",
    "created_at",
    "updated_at",
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_kitchens() -> Dict[str, dict]:
    """Load kitchens.json; return dict keyed by kitchen_id.

    Returns {} if the file is absent or contains only whitespace.
    Raises json.JSONDecodeError if the file contains invalid JSON.
    """
    if not os.path.exists(_KITCHENS_PATH):
        return {}
    with open(_KITCHENS_PATH, encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    # Accept either a dict {id: record} or a list [{kitchen_id: ..., ...}]
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {k["kitchen_id"]: k for k in data if "kitchen_id" in k}
    raise ValueError("kitchens.json must be a JSON object or array")


def load_ngos() -> List[dict]:
    """Load ngos.json; return list of NGO/recipient records.

    Returns [] if the file is absent or empty.
    """
    if not os.path.exists(_NGOS_PATH):
        return []
    with open(_NGOS_PATH, encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.values())
    return []


def load_surplus_log() -> List[dict]:
    """Load surplus_log.csv; return list of surplus row dicts.

    Returns [] if the file is absent or contains only a header / whitespace.
    """
    return _load_csv(_SURPLUS_LOG_PATH)


def load_matches() -> List[dict]:
    """Load matches.csv; return list of match record dicts.

    Returns [] if the file is absent or contains only a header / whitespace.
    """
    return _load_csv(_MATCHES_PATH)


def load_raw_material_log() -> List[dict]:
    """Load raw_material_log.csv; return list of row dicts.

    Returns [] if the file is absent or contains only a header / whitespace.
    """
    return _load_csv(_RAW_MATERIAL_LOG_PATH)


def load_exchange_log() -> List[dict]:
    """Load exchange_log.csv; return list of row dicts.

    Returns [] if the file is absent or contains only a header / whitespace.
    """
    return _load_csv(_EXCHANGE_LOG_PATH)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def save_raw_material_log(rows: List[dict]) -> None:
    """Persist raw_material_log rows to CSV."""
    _save_csv(_RAW_MATERIAL_LOG_PATH, rows, _RAW_MATERIAL_COLUMNS)


def save_exchange_log(rows: List[dict]) -> None:
    """Persist exchange_log rows to CSV."""
    _save_csv(_EXCHANGE_LOG_PATH, rows, _EXCHANGE_COLUMNS)


def save_surplus_log(rows: List[dict]) -> None:
    """Persist surplus_log rows to CSV."""
    _save_csv(_SURPLUS_LOG_PATH, rows, _SURPLUS_COLUMNS)


def save_matches(rows: List[dict]) -> None:
    """Persist matches rows to CSV."""
    _save_csv(_MATCHES_PATH, rows, _MATCHES_COLUMNS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return []
    reader = csv.DictReader(raw.splitlines())
    return [dict(row) for row in reader]


def _save_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
