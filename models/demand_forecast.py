"""
AI-Powered Food Demand Forecasting Module
==========================================
Dataset: train.csv / test.csv + meal_info.csv + fulfilment_center_info.csv
Target : num_orders  (integer weekly order count per center-meal pair)
Model  : RandomForestRegressor (scikit-learn)
         Chosen because the data is tabular with week-based integer time index
         (no calendar dates), center/meal identity features, and price features.
         RF handles mixed feature types, non-linearities, and gives easy
         prediction intervals via per-tree variance — no need for heavy LSTM.

Public interface used by app.py
--------------------------------
    trainer  = DemandForecaster()
    trainer.train()                         # fit model
    result   = trainer.predict(center_id, meal_id, weeks, events=None)
    metrics  = trainer.get_metrics()
    summary  = trainer.get_model_summary()
"""

from __future__ import annotations

import os
import json
import warnings
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BASE_DIR / "datasets"

TRAIN_PATH = DATASETS_DIR / "train.csv"
MEAL_PATH = DATASETS_DIR / "meal_info.csv"
CENTER_PATH = DATASETS_DIR / "fulfilment_center_info.csv"

# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------

def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add cyclical and derived time features from integer week column."""
    df = df.copy()
    df["week_sin"] = np.sin(2 * np.pi * df["week"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week"] / 52)
    df["quarter"] = ((df["week"] - 1) // 13).astype(int) + 1   # 1-4
    df["is_year_end"] = ((df["week"] % 52).isin([51, 52, 1])).astype(int)
    return df


def _price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive discount/price-ratio features."""
    df = df.copy()
    df["price_discount"] = df["base_price"] - df["checkout_price"]
    df["discount_ratio"] = df["price_discount"] / (df["base_price"] + 1e-9)
    return df


def _apply_event_calendar(df: pd.DataFrame, events: list[dict] | None) -> pd.DataFrame:
    """
    Optionally apply event multipliers.

    events: list of dicts with keys:
        week       (int)  — the week number affected
        event_name (str)  — human-readable name
        event_type (str)  — 'holiday' | 'festival' | 'exam' | 'vacation' | 'other'
        multiplier (float, optional) — demand multiplier, default 1.0
    """
    if not events:
        df["event_flag"] = 0
        df["event_multiplier"] = 1.0
        return df

    event_df = pd.DataFrame(events)
    if "week" not in event_df.columns:
        df["event_flag"] = 0
        df["event_multiplier"] = 1.0
        return df

    if "multiplier" not in event_df.columns:
        event_df["multiplier"] = 1.0

    event_map = event_df.groupby("week")["multiplier"].mean().to_dict()
    df["event_flag"] = df["week"].isin(event_map.keys()).astype(int)
    df["event_multiplier"] = df["week"].map(event_map).fillna(1.0)
    return df


FEATURE_COLS = [
    "week",
    "checkout_price",
    "base_price",
    "emailer_for_promotion",
    "homepage_featured",
    "week_sin",
    "week_cos",
    "quarter",
    "is_year_end",
    "price_discount",
    "discount_ratio",
    "event_flag",
    "event_multiplier",
    # encoded categoricals added dynamically
    "center_id",
    "meal_id",
    "category_enc",
    "cuisine_enc",
    "center_type_enc",
    "op_area",
]

TARGET_COL = "num_orders"


# ---------------------------------------------------------------------------
# Main forecaster class
# ---------------------------------------------------------------------------

class DemandForecaster:
    """
    Trains a RandomForest demand forecasting model on the food-delivery
    order history dataset and exposes a clean prediction interface.
    """

    def __init__(self, n_estimators: int = 200, random_state: int = 42):
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._model: RandomForestRegressor | None = None
        self._baseline_model: dict = {}   # center_id+meal_id → mean num_orders
        self._label_encoders: dict[str, LabelEncoder] = {}
        self._feature_cols: list[str] = []
        self._metrics: dict[str, float] = {}
        self._trained = False
        self._train_df: pd.DataFrame | None = None
        self._price_lookup: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if not TRAIN_PATH.exists():
            raise FileNotFoundError(f"Training data not found: {TRAIN_PATH}")
        train = pd.read_csv(TRAIN_PATH)
        meal_info = pd.read_csv(MEAL_PATH)
        center_info = pd.read_csv(CENTER_PATH)
        return train, meal_info, center_info

    def _merge_and_engineer(
        self,
        df: pd.DataFrame,
        meal_info: pd.DataFrame,
        center_info: pd.DataFrame,
        fit_encoders: bool = True,
        events: list[dict] | None = None,
    ) -> pd.DataFrame:
        df = df.copy()

        # Merge meal info
        df = df.merge(meal_info, on="meal_id", how="left")
        # Merge center info
        df = df.merge(center_info, on="center_id", how="left")

        # Fill any missing from merge
        df["category"] = df["category"].fillna("Unknown")
        df["cuisine"] = df["cuisine"].fillna("Unknown")
        df["center_type"] = df["center_type"].fillna("TYPE_A")
        df["op_area"] = df["op_area"].fillna(df["op_area"].median())

        # Label encode categoricals
        for col in ["category", "cuisine", "center_type"]:
            enc_col = f"{col}_enc"
            if fit_encoders:
                le = LabelEncoder()
                df[enc_col] = le.fit_transform(df[col].astype(str))
                self._label_encoders[col] = le
            else:
                le = self._label_encoders.get(col)
                if le is not None:
                    # Handle unseen labels gracefully
                    df[enc_col] = df[col].astype(str).map(
                        lambda x, le=le: (
                            le.transform([x])[0]
                            if x in le.classes_
                            else -1
                        )
                    )
                else:
                    df[enc_col] = 0

        df = _add_time_features(df)
        df = _price_features(df)
        df = _apply_event_calendar(df, events)
        return df

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, events: list[dict] | None = None) -> "DemandForecaster":
        """
        Load data, engineer features, train RandomForest, compute metrics.
        Returns self for chaining.
        """
        logger.info("Loading training data …")
        train_raw, meal_info, center_info = self._load_data()

        logger.info("Engineering features …")
        df = self._merge_and_engineer(
            train_raw, meal_info, center_info, fit_encoders=True, events=events
        )

        # Build baseline: mean num_orders per (center_id, meal_id)
        self._baseline_model = (
            df.groupby(["center_id", "meal_id"])[TARGET_COL]
            .mean()
            .to_dict()
        )

        # Latest price lookup for each (center_id, meal_id) — used in predict
        self._price_lookup = (
            df.sort_values("week")
            .groupby(["center_id", "meal_id"])[
                ["checkout_price", "base_price"]
            ]
            .last()
            .reset_index()
        )
        self._train_df = df

        # Determine available feature columns
        available = [c for c in FEATURE_COLS if c in df.columns]
        self._feature_cols = available

        X = df[self._feature_cols]
        y = df[TARGET_COL]

        # Time-series cross-validation for metrics.
        # Use a subsample (up to 50K rows) for faster CV on large datasets.
        CV_SAMPLE = 50_000
        if len(X) > CV_SAMPLE:
            rng = np.random.default_rng(self.random_state)
            sample_idx = rng.choice(len(X), size=CV_SAMPLE, replace=False)
            sample_idx.sort()  # preserve time order
            X_cv, y_cv = X.iloc[sample_idx], y.iloc[sample_idx]
        else:
            X_cv, y_cv = X, y

        tscv = TimeSeriesSplit(n_splits=3)
        mae_list, rmse_list = [], []
        for X_tr, X_val, y_tr, y_val in (
            (X_cv.iloc[ti], X_cv.iloc[vi], y_cv.iloc[ti], y_cv.iloc[vi])
            for ti, vi in tscv.split(X_cv)
        ):
            tmp = RandomForestRegressor(
                n_estimators=30, random_state=self.random_state, n_jobs=-1
            )
            tmp.fit(X_tr, y_tr)
            preds = tmp.predict(X_val)
            mae_list.append(mean_absolute_error(y_val, preds))
            rmse_list.append(mean_squared_error(y_val, preds) ** 0.5)

        self._metrics = {
            "cv_mae": float(np.mean(mae_list)),
            "cv_rmse": float(np.mean(rmse_list)),
            "cv_folds": len(mae_list),
        }
        # Baseline metrics on subsample for speed
        bl_sample = df.iloc[sample_idx] if len(X) > CV_SAMPLE else df
        bl_preds = bl_sample.apply(
            lambda r: self._baseline_model.get((r["center_id"], r["meal_id"]), float(y.mean())),
            axis=1,
        )
        self._metrics["baseline_mae"] = float(mean_absolute_error(y_cv, bl_preds))
        self._metrics["baseline_rmse"] = float(mean_squared_error(y_cv, bl_preds) ** 0.5)

        logger.info("Training final RandomForest model …")
        self._model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
            min_samples_leaf=5,
        )
        self._model.fit(X, y)
        self._trained = True
        logger.info("Training complete. CV MAE=%.2f  CV RMSE=%.2f",
                    self._metrics["cv_mae"], self._metrics["cv_rmse"])
        return self

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        center_id: int,
        meal_id: int,
        weeks: list[int],
        checkout_price: float | None = None,
        base_price: float | None = None,
        emailer_for_promotion: int = 0,
        homepage_featured: int = 0,
        events: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Predict demand for a given center+meal for a list of week numbers.

        Parameters
        ----------
        center_id            : int
        meal_id              : int
        weeks                : list[int]  e.g. [146, 147, 148, ...]
        checkout_price       : float | None  (uses last known price if None)
        base_price           : float | None
        emailer_for_promotion: 0 or 1
        homepage_featured    : 0 or 1
        events               : optional list of event-calendar dicts

        Returns
        -------
        List of dicts, one per week:
            week, center_id, meal_id, predicted_demand,
            lower_bound, upper_bound, confidence_note
        """
        if not self._trained or self._model is None:
            raise RuntimeError("Model not trained. Call .train() first.")

        # Short-circuit for empty weeks list
        if not weeks:
            return []

        # Resolve prices
        if checkout_price is None or base_price is None:
            row = (
                self._price_lookup[
                    (self._price_lookup["center_id"] == center_id)
                    & (self._price_lookup["meal_id"] == meal_id)
                ]
                if self._price_lookup is not None
                else pd.DataFrame()
            )
            if row.empty:
                # Fall back to overall medians
                cp = float(
                    self._train_df["checkout_price"].median()
                    if self._train_df is not None
                    else 150.0
                )
                bp = float(
                    self._train_df["base_price"].median()
                    if self._train_df is not None
                    else 155.0
                )
            else:
                cp = float(row["checkout_price"].iloc[0])
                bp = float(row["base_price"].iloc[0])
            checkout_price = checkout_price if checkout_price is not None else cp
            base_price = base_price if base_price is not None else bp

        meal_info = pd.read_csv(MEAL_PATH)
        center_info = pd.read_csv(CENTER_PATH)

        rows = []
        for w in weeks:
            rows.append(
                {
                    "week": w,
                    "center_id": center_id,
                    "meal_id": meal_id,
                    "checkout_price": checkout_price,
                    "base_price": base_price,
                    "emailer_for_promotion": emailer_for_promotion,
                    "homepage_featured": homepage_featured,
                }
            )
        pred_df = pd.DataFrame(rows)
        pred_df = self._merge_and_engineer(
            pred_df, meal_info, center_info, fit_encoders=False, events=events
        )

        # Align columns
        for c in self._feature_cols:
            if c not in pred_df.columns:
                pred_df[c] = 0
        X_pred = pred_df[self._feature_cols]

        # Per-tree predictions for uncertainty estimate
        tree_preds = np.array(
            [tree.predict(X_pred) for tree in self._model.estimators_]
        )  # shape: (n_estimators, n_rows)
        mean_pred = tree_preds.mean(axis=0)
        std_pred = tree_preds.std(axis=0)

        results = []
        for i, w in enumerate(weeks):
            p = max(0.0, float(mean_pred[i]))
            std = float(std_pred[i])
            lower = max(0.0, p - 1.96 * std)
            upper = p + 1.96 * std

            # Apply event multiplier post-hoc if supplied
            multiplier = 1.0
            if events:
                ev_match = [e for e in events if e.get("week") == w]
                if ev_match:
                    multiplier = float(ev_match[0].get("multiplier", 1.0))
                    p = p * multiplier
                    lower = lower * multiplier
                    upper = upper * multiplier

            results.append(
                {
                    "week": w,
                    "center_id": center_id,
                    "meal_id": meal_id,
                    "predicted_demand": round(p, 1),
                    "lower_bound": round(lower, 1),
                    "upper_bound": round(upper, 1),
                    "std_dev": round(std, 1),
                    "event_multiplier": multiplier,
                    "confidence_note": (
                        "±95% interval from RF tree variance"
                        + (f"; event multiplier={multiplier}" if multiplier != 1.0 else "")
                    ),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Batch prediction (next N weeks from last known week)
    # ------------------------------------------------------------------

    def forecast_next_n_weeks(
        self,
        center_id: int,
        meal_id: int,
        n: int = 7,
        events: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Convenience wrapper: forecast the next n weeks beyond last training week.
        """
        if self._train_df is None:
            raise RuntimeError("Model not trained. Call .train() first.")
        last_week = int(self._train_df["week"].max())
        weeks = list(range(last_week + 1, last_week + n + 1))
        return self.predict(center_id, meal_id, weeks, events=events)

    # ------------------------------------------------------------------
    # Metrics & summary
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict[str, float]:
        """Return cross-validation metrics dict."""
        if not self._trained:
            raise RuntimeError("Model not trained yet.")
        return dict(self._metrics)

    def get_model_summary(self) -> dict[str, Any]:
        """Return a human-readable model summary dict."""
        if not self._trained:
            raise RuntimeError("Model not trained yet.")
        return {
            "model_type": "RandomForestRegressor",
            "n_estimators": self.n_estimators,
            "feature_cols": self._feature_cols,
            "target": TARGET_COL,
            "training_weeks": int(self._train_df["week"].max()) if self._train_df is not None else None,
            "metrics": self._metrics,
            "dataset": "train.csv + meal_info.csv + fulfilment_center_info.csv",
            "notes": (
                "Week is an integer (1–145 in training). No calendar dates in "
                "original data. Cyclical week features added to capture "
                "within-year seasonality. Event calendar is optional input."
            ),
        }

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> list[dict]:
        """Return feature importances sorted descending."""
        if self._model is None:
            raise RuntimeError("Model not trained yet.")
        imp = self._model.feature_importances_
        return sorted(
            [{"feature": f, "importance": round(float(v), 5)}
             for f, v in zip(self._feature_cols, imp)],
            key=lambda x: x["importance"],
            reverse=True,
        )
