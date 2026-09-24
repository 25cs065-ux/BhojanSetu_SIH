"""
Shared input validators for the BhojanSetu project.

All validator functions raise ValueError on invalid input and return the
(possibly normalised) value on success.  This makes it easy for callers to
write:

    quantity = validate_quantity(raw_quantity)

Public API
----------
VALID_UNITS          : frozenset[str]  – accepted unit strings
validate_ingredient  : str  -> str
validate_quantity    : numeric -> float
validate_unit        : str  -> str    (lower-cased canonical form)
validate_date_str    : str  -> datetime.date
validate_use_by_date : str | None -> datetime.date | None
validate_urgency     : str  -> str    (lower-cased canonical form)
validate_kitchen_id  : str  -> str
"""

import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Accepted vocabulary
# ---------------------------------------------------------------------------

VALID_UNITS: frozenset = frozenset(
    {
        "kg",
        "g",
        "litre",
        "litres",
        "liter",
        "liters",
        "l",
        "ml",
        "piece",
        "pieces",
        "unit",
        "units",
        "dozen",
        "box",
        "boxes",
        "bag",
        "bags",
        "tray",
        "trays",
        "packet",
        "packets",
        "quintal",
        "ton",
        "tons",
        "tonne",
        "tonnes",
    }
)

VALID_URGENCY_LEVELS: frozenset = frozenset({"low", "medium", "high", "critical"})

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_ingredient(value: str) -> str:
    """Return stripped ingredient name; raise ValueError if empty."""
    if not isinstance(value, str):
        raise ValueError(f"Ingredient must be a string, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError("Ingredient name cannot be empty.")
    return stripped


def validate_quantity(value) -> float:
    """Return quantity as float; raise ValueError if not positive."""
    try:
        qty = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Quantity must be a number, got {value!r}")
    if qty <= 0:
        raise ValueError(f"Quantity must be positive, got {qty}")
    return qty


def validate_unit(value: str) -> str:
    """Return lower-cased unit; raise ValueError if not in VALID_UNITS."""
    if not isinstance(value, str):
        raise ValueError(f"Unit must be a string, got {type(value).__name__}")
    normalised = value.strip().lower()
    if normalised not in VALID_UNITS:
        raise ValueError(
            f"Unit {value!r} is not valid. Accepted units: {sorted(VALID_UNITS)}"
        )
    return normalised


def validate_date_str(value: str) -> datetime.date:
    """Parse a date string into a datetime.date; raise ValueError on failure."""
    if not isinstance(value, str):
        raise ValueError(f"Date must be a string, got {type(value).__name__}")
    stripped = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Date {value!r} could not be parsed. Expected formats: YYYY-MM-DD, "
        f"DD-MM-YYYY, DD/MM/YYYY, YYYY/MM/DD"
    )


def validate_use_by_date(value: Optional[str]) -> Optional[datetime.date]:
    """Parse an optional use-by date string.

    Returns None if value is None or empty string.
    Raises ValueError for a non-empty string that cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return validate_date_str(value)


def validate_urgency(value: str) -> str:
    """Return lower-cased urgency level; raise ValueError if not recognised."""
    if not isinstance(value, str):
        raise ValueError(f"Urgency must be a string, got {type(value).__name__}")
    normalised = value.strip().lower()
    if normalised not in VALID_URGENCY_LEVELS:
        raise ValueError(
            f"Urgency {value!r} is not valid. Accepted levels: "
            f"{sorted(VALID_URGENCY_LEVELS)}"
        )
    return normalised


def validate_kitchen_id(value: str) -> str:
    """Return stripped kitchen ID; raise ValueError if empty."""
    if not isinstance(value, str):
        raise ValueError(f"Kitchen ID must be a string, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError("Kitchen ID cannot be empty.")
    return stripped
