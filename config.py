"""
BhojanSetu — Central configuration
All paths are relative to PROJECT_ROOT so the application works regardless
of the directory from which Flask is started.
"""

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent

# ── Application data (runtime-generated) ─────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"

# ── Source / reference datasets (READ-ONLY) ──────────────────────────────────
DATASET_DIR = PROJECT_ROOT / "datasets"

# ── PDF reports output ────────────────────────────────────────────────────────
REPORTS_DIR = PROJECT_ROOT / "reports"

# ── Static assets ─────────────────────────────────────────────────────────────
STATIC_DIR = PROJECT_ROOT / "static"

# ── Application data files ────────────────────────────────────────────────────
USERS_FILE            = DATA_DIR / "users.json"
KITCHENS_FILE         = DATA_DIR / "kitchens.json"
NGOS_FILE             = DATA_DIR / "ngos.json"
SURPLUS_LOG_FILE      = DATA_DIR / "surplus_log.csv"
RAW_MATERIAL_LOG_FILE = DATA_DIR / "raw_material_log.csv"
MATCHES_FILE          = DATA_DIR / "matches.csv"
EXCHANGE_LOG_FILE     = DATA_DIR / "exchange_log.csv"
PRODUCTION_PLAN_FILE  = DATA_DIR / "production_plan.csv"
SUSTAINABILITY_LOG_FILE = DATA_DIR / "sustainability_log.csv"

# ── Source datasets ───────────────────────────────────────────────────────────
TRAIN_CSV                   = DATASET_DIR / "train.csv"
TEST_CSV                    = DATASET_DIR / "test.csv"
MEAL_INFO_CSV               = DATASET_DIR / "meal_info.csv"
FULFILMENT_CENTER_INFO_CSV  = DATASET_DIR / "fulfilment_center_info.csv"
FOOD_WASTAGE_CSV            = DATASET_DIR / "food_wastage_data.csv"
GLOBAL_FOOD_WASTAGE_CSV     = DATASET_DIR / "global_food_wastage_dataset.csv"
INDIAN_NUTRITION_CSV        = DATASET_DIR / "Indian_Food_Nutrition_Processed.csv"
INDIAN_FOOD_CSV             = DATASET_DIR / "indian_food.csv"
FOOD_PRODUCTION_CSV         = DATASET_DIR / "Food_Production.csv"

# ── Flask settings ────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("BHOJANSETU_SECRET", "bhojansetu-dev-secret-2024")
SESSION_COOKIE_SECURE = False   # set True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# ── Ensure required directories exist ────────────────────────────────────────
for _d in (DATA_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
