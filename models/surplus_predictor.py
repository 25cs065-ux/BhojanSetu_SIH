"""
Surplus Prediction Engine
==========================
Concept
-------
    Estimated Surplus = Prepared Quantity - Predicted Consumption

This module wraps the DemandForecaster output and converts it into a
structured surplus risk assessment.  No second heavy ML model is used;
the arithmetic is deterministic once the demand forecast is known.

An optional historical over-preparation factor (op_factor) can be supplied
to account for kitchens that consistently prepare more than forecast.

Public interface used by app.py
--------------------------------
    engine   = SurplusPredictor()
    result   = engine.calculate(prepared_qty, forecast_demand, item_name="")
    results  = engine.batch_calculate(prepared_list, forecast_list)
    risk     = engine.classify_risk(surplus_pct)

Risk thresholds (configurable)
--------------------------------
    LOW     : surplus_pct  <  10 %
    MEDIUM  : surplus_pct  10 – 25 %
    HIGH    : surplus_pct  >  25 %
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Risk thresholds (can be overridden at instantiation)
# ---------------------------------------------------------------------------
DEFAULT_LOW_THRESHOLD = 10.0    # percent
DEFAULT_HIGH_THRESHOLD = 25.0   # percent


class SurplusPredictor:
    """
    Converts a demand forecast into a surplus risk assessment.

    Parameters
    ----------
    low_threshold  : float
        Surplus percentage below which risk is LOW (default 10 %).
    high_threshold : float
        Surplus percentage above which risk is HIGH (default 25 %).
    op_factor      : float
        Over-preparation adjustment factor applied to prepared_qty when
        historical data shows consistent over-preparation.
        E.g. op_factor=0.95 reduces effective prepared qty by 5 % for
        a fairer comparison. Default 1.0 (no adjustment).
    """

    def __init__(
        self,
        low_threshold: float = DEFAULT_LOW_THRESHOLD,
        high_threshold: float = DEFAULT_HIGH_THRESHOLD,
        op_factor: float = 1.0,
    ):
        if low_threshold >= high_threshold:
            raise ValueError(
                f"low_threshold ({low_threshold}) must be less than "
                f"high_threshold ({high_threshold})."
            )
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.op_factor = op_factor

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------

    def calculate(
        self,
        prepared_qty: float,
        forecast_demand: float,
        item_name: str = "",
        unit: str = "units",
        week: int | None = None,
        center_id: int | None = None,
        meal_id: int | None = None,
        lower_bound: float | None = None,
        upper_bound: float | None = None,
    ) -> dict[str, Any]:
        """
        Calculate surplus for a single item/week.

        Parameters
        ----------
        prepared_qty    : float — quantity prepared (kg / portions / units)
        forecast_demand : float — predicted consumption from DemandForecaster
        item_name       : str   — human-readable label
        unit            : str   — unit of measurement
        week            : int   — week number (informational)
        center_id       : int   — kitchen/center id (informational)
        meal_id         : int   — meal id (informational)
        lower_bound     : float — lower bound from forecast (optional)
        upper_bound     : float — upper bound from forecast (optional)

        Returns
        -------
        dict with keys:
            item_name, week, center_id, meal_id,
            prepared_qty, forecast_demand, estimated_surplus,
            surplus_pct, risk_level, explanation,
            lower_bound, upper_bound,
            worst_case_surplus, best_case_surplus
        """
        if prepared_qty < 0:
            raise ValueError(f"prepared_qty must be >= 0, got {prepared_qty}")
        if forecast_demand < 0:
            raise ValueError(f"forecast_demand must be >= 0, got {forecast_demand}")

        # Apply over-preparation factor to effective prepared qty
        effective_prepared = prepared_qty * self.op_factor

        surplus = effective_prepared - forecast_demand
        surplus_pct = (
            (surplus / effective_prepared * 100.0) if effective_prepared > 0 else 0.0
        )
        risk_level = self.classify_risk(surplus_pct)

        # Worst/best case using forecast bounds
        worst_surplus = (
            (effective_prepared - lower_bound)
            if lower_bound is not None
            else None
        )
        best_surplus = (
            (effective_prepared - upper_bound)
            if upper_bound is not None
            else None
        )

        explanation = self._build_explanation(
            item_name, prepared_qty, forecast_demand, surplus, surplus_pct, risk_level, unit
        )

        return {
            "item_name": item_name,
            "week": week,
            "center_id": center_id,
            "meal_id": meal_id,
            "unit": unit,
            "prepared_qty": round(prepared_qty, 2),
            "effective_prepared_qty": round(effective_prepared, 2),
            "forecast_demand": round(forecast_demand, 2),
            "estimated_surplus": round(surplus, 2),
            "surplus_pct": round(surplus_pct, 1),
            "risk_level": risk_level,
            "explanation": explanation,
            "lower_bound": round(lower_bound, 2) if lower_bound is not None else None,
            "upper_bound": round(upper_bound, 2) if upper_bound is not None else None,
            "worst_case_surplus": round(worst_surplus, 2) if worst_surplus is not None else None,
            "best_case_surplus": round(best_surplus, 2) if best_surplus is not None else None,
        }

    # ------------------------------------------------------------------
    # Batch calculation
    # ------------------------------------------------------------------

    def batch_calculate(
        self,
        prepared_list: list[float],
        forecast_records: list[dict],
        unit: str = "units",
    ) -> list[dict[str, Any]]:
        """
        Calculate surplus for a list of (prepared_qty, forecast_record) pairs.

        Parameters
        ----------
        prepared_list    : list[float] — one prepared quantity per record
        forecast_records : list[dict]  — output rows from DemandForecaster.predict()

        Returns
        -------
        List of surplus dicts (same schema as calculate())
        """
        if len(prepared_list) != len(forecast_records):
            raise ValueError(
                f"prepared_list length ({len(prepared_list)}) must match "
                f"forecast_records length ({len(forecast_records)})."
            )
        results = []
        for qty, rec in zip(prepared_list, forecast_records):
            results.append(
                self.calculate(
                    prepared_qty=qty,
                    forecast_demand=rec.get("predicted_demand", 0.0),
                    item_name=str(rec.get("meal_id", "")),
                    unit=unit,
                    week=rec.get("week"),
                    center_id=rec.get("center_id"),
                    meal_id=rec.get("meal_id"),
                    lower_bound=rec.get("lower_bound"),
                    upper_bound=rec.get("upper_bound"),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Risk classification
    # ------------------------------------------------------------------

    def classify_risk(self, surplus_pct: float) -> str:
        """
        Classify surplus risk.

        Returns 'LOW', 'MEDIUM', or 'HIGH'.
        Negative surplus (under-preparation) is classified separately.
        """
        if surplus_pct < 0:
            return "SHORTAGE"      # prepared less than forecast
        if surplus_pct < self.low_threshold:
            return "LOW"
        if surplus_pct <= self.high_threshold:
            return "MEDIUM"
        return "HIGH"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_explanation(
        item_name: str,
        prepared_qty: float,
        forecast_demand: float,
        surplus: float,
        surplus_pct: float,
        risk_level: str,
        unit: str,
    ) -> str:
        name = item_name if item_name else "item"
        if risk_level == "SHORTAGE":
            return (
                f"Prepared {prepared_qty:.1f} {unit} of {name}, "
                f"but forecast demand is {forecast_demand:.1f} {unit}. "
                f"Potential shortage of {abs(surplus):.1f} {unit}. "
                f"Consider increasing preparation quantity."
            )
        messages = {
            "LOW": (
                f"Prepared {prepared_qty:.1f} {unit} vs forecast {forecast_demand:.1f} {unit}. "
                f"Estimated surplus {surplus:.1f} {unit} ({surplus_pct:.1f}%). "
                f"Low risk — surplus within acceptable range."
            ),
            "MEDIUM": (
                f"Prepared {prepared_qty:.1f} {unit} vs forecast {forecast_demand:.1f} {unit}. "
                f"Estimated surplus {surplus:.1f} {unit} ({surplus_pct:.1f}%). "
                f"Medium risk — consider reducing preparation or arranging redistribution."
            ),
            "HIGH": (
                f"Prepared {prepared_qty:.1f} {unit} vs forecast {forecast_demand:.1f} {unit}. "
                f"Estimated surplus {surplus:.1f} {unit} ({surplus_pct:.1f}%). "
                f"HIGH risk — significant over-preparation. "
                f"Immediate redistribution planning recommended."
            ),
        }
        return messages.get(risk_level, "Unknown risk level.")

    # ------------------------------------------------------------------
    # Summary helpers (for frontend / API)
    # ------------------------------------------------------------------

    def summarise_batch(self, batch_results: list[dict]) -> dict[str, Any]:
        """
        Aggregate a batch result into a high-level summary.
        """
        if not batch_results:
            return {}
        total_prepared = sum(r["prepared_qty"] for r in batch_results)
        total_forecast = sum(r["forecast_demand"] for r in batch_results)
        total_surplus = sum(r["estimated_surplus"] for r in batch_results)
        overall_pct = (
            total_surplus / total_prepared * 100 if total_prepared > 0 else 0.0
        )
        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "SHORTAGE": 0}
        for r in batch_results:
            rl = r.get("risk_level", "LOW")
            risk_counts[rl] = risk_counts.get(rl, 0) + 1

        return {
            "total_prepared": round(total_prepared, 2),
            "total_forecast": round(total_forecast, 2),
            "total_surplus": round(total_surplus, 2),
            "overall_surplus_pct": round(overall_pct, 1),
            "overall_risk": self.classify_risk(overall_pct),
            "risk_distribution": risk_counts,
            "weeks_count": len(batch_results),
        }
