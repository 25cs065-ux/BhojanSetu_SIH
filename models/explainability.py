"""
Explainable AI Insights Panel — Feature 10
Explains why an AI/ML model produced a particular prediction.

Design principles:
- Inspects the actual model object to determine explanation method.
- Never fabricates feature importance or coefficients.
- If an explanation is not available for a given model type,
  returns EXPLAINABILITY_NOT_AVAILABLE rather than inventing one.
- Supports: LinearRegression, Ridge, Lasso (coefficients),
            RandomForest / GradientBoosting (feature_importances_),
            Prophet (component contributions),
            generic sklearn (coef_ / feature_importances_ if present).

Member 2's demand_forecast.py is currently an empty stub.
This module is written to gracefully inspect whatever model is passed in,
and return a meaningful explanation or a clear "not available" response.
"""

from __future__ import annotations

import os
import traceback
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Public constant — used in tests
# ──────────────────────────────────────────────────────────────────────────────
EXPLAINABILITY_NOT_AVAILABLE = (
    "Explainability information is not available for this model."
)


# ──────────────────────────────────────────────────────────────────────────────
# Optional heavy imports — never crash if missing
# ──────────────────────────────────────────────────────────────────────────────
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _not_available(reason: str = "") -> dict[str, Any]:
    return {
        "explainable": False,
        "message": EXPLAINABILITY_NOT_AVAILABLE,
        "reason": reason or "Model type not recognised or does not expose explainability.",
    }


def _round_if_float(v: Any, decimals: int = 6) -> Any:
    try:
        return round(float(v), decimals)
    except (TypeError, ValueError):
        return v


def _to_list(arr: Any) -> list:
    """Convert numpy arrays or pandas Series to a flat plain Python list."""
    if arr is None:
        return []
    try:
        # Flatten 2-D arrays (e.g. multi-output LinearRegression coef_)
        if _NUMPY_AVAILABLE:
            import numpy as _np
            if isinstance(arr, _np.ndarray) and arr.ndim == 2:
                arr = arr.flatten()
        return [_round_if_float(x) for x in arr]
    except TypeError:
        return [_round_if_float(arr)]


# ──────────────────────────────────────────────────────────────────────────────
# Explanation strategies
# ──────────────────────────────────────────────────────────────────────────────

def _explain_linear(model: Any, feature_names: list[str] | None) -> dict[str, Any]:
    """
    Explain a linear model (LinearRegression, Ridge, Lasso, etc.).
    Uses model.coef_ and model.intercept_.
    """
    coef = getattr(model, "coef_", None)
    intercept = getattr(model, "intercept_", None)

    if coef is None:
        return _not_available("Linear model has no coef_ attribute.")

    coef_list = _to_list(coef)
    # intercept_ may be a scalar float or a 1-element numpy array
    try:
        if hasattr(intercept, "__len__"):
            intercept_val = _round_if_float(float(list(intercept)[0]))
        else:
            intercept_val = _round_if_float(intercept)
    except (TypeError, IndexError, ValueError):
        intercept_val = None

    if feature_names and len(feature_names) == len(coef_list):
        coef_map = {str(fn): c for fn, c in zip(feature_names, coef_list)}
        ranked = sorted(coef_map.items(), key=lambda x: abs(x[1]), reverse=True)
    else:
        coef_map = {f"feature_{i}": c for i, c in enumerate(coef_list)}
        ranked = sorted(coef_map.items(), key=lambda x: abs(x[1]), reverse=True)

    factors = []
    for fname, coef_val in ranked:
        direction = "increases" if coef_val > 0 else "decreases"
        factors.append({
            "feature": fname,
            "coefficient": coef_val,
            "effect": (
                f"A unit increase in '{fname}' {direction} "
                f"the prediction by {abs(coef_val):.6f}."
            ),
        })

    return {
        "explainable": True,
        "method": "linear_coefficients",
        "description": (
            "Linear model coefficients show the weight of each feature. "
            "Larger absolute coefficient = stronger influence on prediction."
        ),
        "intercept": intercept_val,
        "coefficients": coef_map,
        "ranked_factors": factors,
        "interpretation_note": (
            "Coefficients are in the units of the target variable per unit "
            "of each feature. Sign indicates direction of influence."
        ),
    }


def _explain_tree_ensemble(model: Any, feature_names: list[str] | None) -> dict[str, Any]:
    """
    Explain a tree-based ensemble (RandomForest, GradientBoosting, etc.).
    Uses model.feature_importances_.
    """
    fi = getattr(model, "feature_importances_", None)
    if fi is None:
        return _not_available("Tree model has no feature_importances_ attribute.")

    fi_list = _to_list(fi)

    if feature_names and len(feature_names) == len(fi_list):
        fi_map = {str(fn): v for fn, v in zip(feature_names, fi_list)}
    else:
        fi_map = {f"feature_{i}": v for i, v in enumerate(fi_list)}

    ranked = sorted(fi_map.items(), key=lambda x: x[1], reverse=True)

    factors = [
        {
            "feature": fname,
            "importance": imp,
            "effect": f"'{fname}' explains {imp:.2%} of the model's decision-making.",
        }
        for fname, imp in ranked
    ]

    return {
        "explainable": True,
        "method": "feature_importances",
        "description": (
            "Tree-based feature importances (mean decrease in impurity). "
            "Higher = more influential in predictions."
        ),
        "feature_importances": fi_map,
        "ranked_factors": factors,
        "interpretation_note": (
            "Importances are normalised to sum to 1.0. "
            "They reflect overall importance across all training samples, "
            "not the specific prediction input."
        ),
    }


def _explain_prophet(model: Any, prediction_input: Any) -> dict[str, Any]:
    """
    Explain a Prophet forecast.
    Prophet predictions decompose into trend + seasonality components.
    prediction_input should be the forecast DataFrame from model.predict().
    """
    if not _PANDAS_AVAILABLE:
        return _not_available("pandas is required for Prophet explanation.")

    # prediction_input may be the forecast df already
    try:
        if _PANDAS_AVAILABLE and hasattr(prediction_input, "columns"):
            forecast = prediction_input
        else:
            return _not_available(
                "Prophet explanation requires the forecast DataFrame "
                "from model.predict() as prediction_input."
            )

        available_components = [
            c for c in forecast.columns
            if c not in ("ds", "yhat", "yhat_lower", "yhat_upper")
            and not c.endswith(("_lower", "_upper"))
        ]

        components: dict[str, Any] = {}
        for comp in available_components:
            try:
                series = forecast[comp].dropna()
                if len(series) > 0:
                    components[comp] = {
                        "mean":  round(float(series.mean()), 4),
                        "last":  round(float(series.iloc[-1]), 4),
                        "min":   round(float(series.min()), 4),
                        "max":   round(float(series.max()), 4),
                    }
            except Exception:
                pass

        if not components:
            return _not_available("No decomposable components found in Prophet forecast.")

        factors = []
        for comp, stats in components.items():
            direction = "upward" if stats["last"] > 0 else "downward"
            factors.append({
                "component": comp,
                "latest_contribution": stats["last"],
                "effect": (
                    f"The '{comp}' component contributes {stats['last']:+.4f} "
                    f"({direction} influence) to the forecast."
                ),
            })

        return {
            "explainable": True,
            "method": "prophet_components",
            "description": (
                "Prophet decomposes predictions into trend + seasonality components. "
                "Each component's contribution to the final forecast is shown."
            ),
            "components": components,
            "ranked_factors": sorted(
                factors, key=lambda x: abs(x["latest_contribution"]), reverse=True
            ),
            "interpretation_note": (
                "trend: long-term direction. "
                "weekly: day-of-week effect. "
                "yearly: seasonal effect. "
                "holidays/extra regressors: event effects (if configured)."
            ),
        }

    except Exception as e:
        return _not_available(f"Prophet explanation failed: {e}")


def _explain_generic_sklearn(model: Any, feature_names: list[str] | None) -> dict[str, Any]:
    """
    Attempt explanation for any sklearn-compatible model.
    Tries coef_ first, then feature_importances_.
    """
    if hasattr(model, "coef_"):
        return _explain_linear(model, feature_names)
    if hasattr(model, "feature_importances_"):
        return _explain_tree_ensemble(model, feature_names)
    return _not_available(
        f"Model of type '{type(model).__name__}' does not expose coef_ or feature_importances_."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Model type detection
# ──────────────────────────────────────────────────────────────────────────────

_LINEAR_TYPES = {
    "LinearRegression", "Ridge", "Lasso", "ElasticNet",
    "BayesianRidge", "HuberRegressor", "SGDRegressor",
    "LogisticRegression", "LinearSVC",
}

_TREE_ENSEMBLE_TYPES = {
    "RandomForestRegressor", "RandomForestClassifier",
    "GradientBoostingRegressor", "GradientBoostingClassifier",
    "ExtraTreesRegressor", "ExtraTreesClassifier",
    "AdaBoostRegressor", "AdaBoostClassifier",
    "DecisionTreeRegressor", "DecisionTreeClassifier",
    "XGBRegressor", "XGBClassifier",
    "LGBMRegressor", "LGBMClassifier",
}

_PROPHET_TYPES = {"Prophet"}


def _detect_model_type(model: Any, model_type_hint: str | None) -> str:
    if model_type_hint:
        hint = model_type_hint.lower().replace("-", "_").replace(" ", "_")
        if "linear" in hint or "regression" in hint or "ridge" in hint or "lasso" in hint:
            return "linear"
        if "forest" in hint or "tree" in hint or "boost" in hint or "xgb" in hint or "lgbm" in hint:
            return "tree_ensemble"
        if "prophet" in hint:
            return "prophet"
        return hint

    if model is None:
        return "none"

    class_name = type(model).__name__
    if class_name in _LINEAR_TYPES:
        return "linear"
    if class_name in _TREE_ENSEMBLE_TYPES:
        return "tree_ensemble"
    if class_name in _PROPHET_TYPES:
        return "prophet"
    # Fallback: inspect attributes
    if hasattr(model, "coef_") or hasattr(model, "feature_importances_"):
        return "generic_sklearn"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def explain_prediction(
    model: Any,
    prediction_input: Any = None,
    model_type: str | None = None,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Explain why a model produced a prediction.

    Parameters
    ----------
    model : Any
        The trained model object. May be None (returns not-available gracefully).
    prediction_input : Any
        Input data used for the prediction (numpy array, DataFrame, etc.).
        Required for Prophet (pass the forecast DataFrame).
    model_type : str or None
        Optional hint: 'linear_regression', 'random_forest', 'prophet', etc.
        If not provided, the model class name is inspected automatically.
    feature_names : list of str or None
        Optional feature names to annotate coefficients/importances.

    Returns
    -------
    dict with keys:
        explainable (bool), method (str), description (str),
        ranked_factors (list), ... model-specific fields.
    If not available: explainable=False, message=EXPLAINABILITY_NOT_AVAILABLE.
    """
    if model is None:
        return _not_available("No model provided (model is None).")

    try:
        detected = _detect_model_type(model, model_type)

        if detected == "none":
            return _not_available("No model provided.")

        if detected == "linear":
            result = _explain_linear(model, feature_names)
        elif detected == "tree_ensemble":
            result = _explain_tree_ensemble(model, feature_names)
        elif detected == "prophet":
            result = _explain_prophet(model, prediction_input)
        elif detected == "generic_sklearn":
            result = _explain_generic_sklearn(model, feature_names)
        elif detected == "unknown":
            result = _not_available(
                f"Model type '{type(model).__name__}' is not recognised. "
                "Supported types: linear (coef_), tree ensemble (feature_importances_), Prophet."
            )
        else:
            result = _not_available(
                f"Explanation strategy for model_type='{detected}' is not implemented."
            )

        result["model_class"] = type(model).__name__
        result["detected_type"] = detected
        return result

    except Exception as e:
        return {
            "explainable": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "message": EXPLAINABILITY_NOT_AVAILABLE,
            "reason": "An unexpected error occurred during explanation.",
        }


def get_demand_forecast_explanation(
    forecast_result: dict | None = None,
    model: Any = None,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for Member 2's demand_forecast module.
    Attempts to import and inspect the demand forecasting model.
    Falls back gracefully if the model is not yet implemented.
    """
    # Try to import Member 2's module
    try:
        import importlib
        df_module = importlib.import_module("models.demand_forecast")

        # Look for a trained model or forecast explanation hook
        if hasattr(df_module, "get_model"):
            model = df_module.get_model()
        elif hasattr(df_module, "MODEL"):
            model = df_module.MODEL
        else:
            model = None

        if model is None:
            return _not_available(
                "demand_forecast module loaded but no trained model found. "
                "Member 2's model may not yet be trained."
            )

        return explain_prediction(model=model, feature_names=feature_names)

    except (ImportError, ModuleNotFoundError):
        return _not_available("demand_forecast module could not be imported.")
    except Exception as e:
        return _not_available(f"Error loading demand_forecast model: {e}")
