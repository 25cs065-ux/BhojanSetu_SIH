"""
app.py — BhojanSetu Flask Application
======================================
Single integrated Flask application that wires together all team modules:
  - Authentication (Member 1 / integration)
  - Demand Forecasting + Surplus Prediction (Member 2)
  - Matching Engine + Nutrition Matcher + Route Optimizer (Member 3)
  - Production Planner + Sustainability + Report + Explainability (Member 4)
  - Frontend templates (Member 5)
  - Data layer utilities (Member 6)

Run with:
    python app.py
or
    flask --app app run --debug
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, jsonify, redirect, render_template,
    request, send_file, session, url_for, flash
)

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bhojansetu")

# ---------------------------------------------------------------------------
# Create Flask app
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.secret_key = config.SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = config.SESSION_COOKIE_HTTPONLY
app.config["SESSION_COOKIE_SAMESITE"] = config.SESSION_COOKIE_SAMESITE

# ---------------------------------------------------------------------------
# Register auth blueprint
# ---------------------------------------------------------------------------
from auth.routes import auth_bp
app.register_blueprint(auth_bp)

# ---------------------------------------------------------------------------
# Login-required decorator
# ---------------------------------------------------------------------------

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                return render_template("login.html"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Lazy-loaded ML model (loaded once in background thread on startup)
# ---------------------------------------------------------------------------

_demand_model = None
_demand_model_lock = threading.Lock()
_demand_model_ready = False
_demand_model_error: str | None = None


def _load_demand_model():
    global _demand_model, _demand_model_ready, _demand_model_error
    try:
        from models.demand_forecast import DemandForecaster
        forecaster = DemandForecaster(n_estimators=100, random_state=42)
        forecaster.train()
        with _demand_model_lock:
            _demand_model = forecaster
            _demand_model_ready = True
        logger.info("Demand forecasting model trained and ready.")
    except Exception as exc:
        with _demand_model_lock:
            _demand_model_error = str(exc)
        logger.error("Demand model training failed: %s", exc)


def _get_demand_model():
    with _demand_model_lock:
        return _demand_model, _demand_model_ready, _demand_model_error


# ---------------------------------------------------------------------------
# Data layer helpers (thin wrappers around utils/data_loader.py)
# ---------------------------------------------------------------------------

from utils.data_loader import (
    load_kitchens,
    load_ngos,
    load_surplus_log,
    load_matches,
    load_raw_material_log,
    load_exchange_log,
    save_surplus_log,
    save_matches,
    save_raw_material_log,
    save_exchange_log,
)

# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        role = session.get("role", "kitchen")
        ep = {"kitchen": "dashboard_kitchen", "ngo": "dashboard_ngo", "admin": "dashboard_admin"}
        return redirect(url_for(ep.get(role, "dashboard_kitchen")))
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------

@app.route("/dashboard/kitchen")
@login_required
def dashboard_kitchen():
    return render_template("dashboard_kitchen.html")


@app.route("/dashboard/ngo")
@login_required
def dashboard_ngo():
    return render_template("dashboard_ngo.html")


@app.route("/dashboard/admin")
@login_required
def dashboard_admin():
    return render_template("dashboard_admin.html")


@app.route("/ngo-matches")
@login_required
def ngo_matches():
    return render_template("ngo_matches.html")


@app.route("/route-map")
@login_required
def route_map():
    return render_template("route_map.html")


@app.route("/surplus-exchange")
@login_required
def surplus_exchange():
    return render_template("surplus_exchange.html")


@app.route("/production-planning")
@login_required
def production_planning():
    return render_template("production_planning.html")


@app.route("/sustainability")
@login_required
def sustainability_report():
    return render_template("sustainability_report.html")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _ok(data):
    return jsonify(data), 200


def _err(msg, code=400):
    return jsonify({"error": msg, "message": msg}), code


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_kitchen_id() -> str:
    """Return the kitchen_id associated with the logged-in user.
    Falls back to matching by institution name, then to 'K001'."""
    institution = session.get("institution", "")
    kitchens = load_kitchens()
    for kid, k in kitchens.items():
        if k.get("name", "").strip().lower() == institution.strip().lower():
            return kid
    # Just return the first kitchen as a sensible fallback
    if kitchens:
        return next(iter(kitchens))
    return "K001"


# ===========================================================================
# API — DEMAND FORECASTING (Feature 1 + 2)
# ===========================================================================

@app.route("/api/demand")
@login_required
def api_demand():
    """
    GET /api/demand?meal_id=<int>&weeks=<int>&center_id=<int>&prepared_qty=<float>

    Returns:
        { forecast: [...], surplus_summary: {...}, explanation: {...} }
    """
    try:
        meal_id_raw  = request.args.get("meal_id", "")
        weeks_raw    = request.args.get("weeks", "7")
        center_id_raw = request.args.get("center_id", "")
        prepared_raw = request.args.get("prepared_qty", "")

        weeks = min(int(weeks_raw), 52)

        model, ready, error = _get_demand_model()

        if not ready:
            if error:
                return _err(f"Demand model not available: {error}", 503)
            return _err("Demand model is still loading. Please retry in a moment.", 503)

        # Determine center_id and meal_id
        # If not supplied, use reasonable defaults from the training data
        try:
            center_id = int(center_id_raw) if center_id_raw else _pick_default_center(model)
        except ValueError:
            center_id = _pick_default_center(model)

        try:
            meal_id = int(meal_id_raw) if meal_id_raw else _pick_default_meal(model)
        except ValueError:
            meal_id = _pick_default_meal(model)

        forecast = model.forecast_next_n_weeks(
            center_id=center_id,
            meal_id=meal_id,
            n=weeks,
        )

        # Feature 2: Surplus prediction
        surplus_summary = None
        if prepared_raw:
            try:
                prepared_qty = float(prepared_raw)
                from models.surplus_predictor import SurplusPredictor
                sp = SurplusPredictor()
                if forecast:
                    avg_demand = sum(r["predicted_demand"] for r in forecast) / len(forecast)
                    surplus_summary = sp.calculate(
                        prepared_qty=prepared_qty,
                        forecast_demand=avg_demand,
                        item_name=f"Meal {meal_id}",
                        week=forecast[0].get("week"),
                        center_id=center_id,
                        meal_id=meal_id,
                        lower_bound=forecast[0].get("lower_bound"),
                        upper_bound=forecast[0].get("upper_bound"),
                    )
            except (ValueError, TypeError) as exc:
                logger.warning("Surplus calculation error: %s", exc)

        # Feature 10: Explainability
        explanation = None
        try:
            from models.explainability import explain_prediction
            explanation = explain_prediction(
                model=model._model,
                feature_names=model._feature_cols,
            )
        except Exception as exc:
            logger.warning("Explainability error: %s", exc)
            explanation = {"explainable": False, "message": str(exc)}

        return _ok({
            "forecast":        forecast,
            "surplus_summary": surplus_summary,
            "explanation":     explanation,
            "center_id":       center_id,
            "meal_id":         meal_id,
            "weeks":           weeks,
        })

    except Exception as exc:
        logger.error("api_demand error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


def _pick_default_center(model) -> int:
    """Pick a representative center_id from training data."""
    try:
        return int(model._train_df["center_id"].mode()[0])
    except Exception:
        return 11  # fallback to a known id in the fulfilment_center dataset


def _pick_default_meal(model) -> int:
    """Pick a representative meal_id from training data."""
    try:
        return int(model._train_df["meal_id"].mode()[0])
    except Exception:
        return 1885  # fallback


@app.route("/api/meals")
@login_required
def api_meals():
    """Return available meal_id / center_id pairs for the forecast UI selector."""
    model, ready, _ = _get_demand_model()
    if not ready or model is None:
        return _ok({"meals": [], "centers": []})
    try:
        meals = sorted(model._train_df["meal_id"].unique().tolist())[:50]
        centers = sorted(model._train_df["center_id"].unique().tolist())[:30]
        return _ok({"meals": meals, "centers": centers})
    except Exception as exc:
        return _err(str(exc), 500)


# ===========================================================================
# API — SURPLUS LOG (Feature 2)
# ===========================================================================

@app.route("/api/surplus", methods=["GET", "POST"])
@login_required
def api_surplus():
    if request.method == "GET":
        rows = load_surplus_log()
        # Filter by kitchen if role is kitchen
        if session.get("role") == "kitchen":
            kid = _get_kitchen_id()
            rows = [r for r in rows if r.get("kitchen_id") == kid]
        # KPI: total surplus kg this month
        now = datetime.now()
        month_kg = 0.0
        for r in rows:
            try:
                d = datetime.strptime(r.get("date_of_surplus", "")[:10], "%Y-%m-%d")
                if d.year == now.year and d.month == now.month:
                    month_kg += float(r.get("quantity_kg", 0))
            except (ValueError, TypeError):
                pass
        return _ok({"items": rows, "total_this_month_kg": round(month_kg, 2)})

    # POST — log new surplus
    data = request.get_json(silent=True) or {}
    try:
        from models.matching_engine import make_surplus_record
        kitchen_id = _get_kitchen_id()
        record = make_surplus_record(
            kitchen_id=kitchen_id,
            food_item=data.get("food_item", ""),
            quantity_kg=data.get("quantity_kg", 0),
            date_of_surplus=data.get("date_of_surplus", ""),
            expiry_time_hours=data.get("expiry_time_hours", 0),
            urgency=data.get("urgency", "medium"),
        )
        rows = load_surplus_log()
        rows.append(record.to_dict())
        save_surplus_log(rows)
        return _ok({"message": "Surplus logged successfully.", "surplus_id": record.surplus_id})
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:
        logger.error("api_surplus POST error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


# ===========================================================================
# API — NGO MATCHING + NUTRITION (Feature 4 + 5)
# ===========================================================================

@app.route("/api/matches", methods=["GET", "POST"])
@login_required
def api_matches():
    if request.method == "GET":
        # GET all stored matches (for admin / NGO view)
        rows = load_matches()
        return _ok({"matches": rows})

    # POST — this endpoint is unused directly; confirm is separate
    return _err("Use GET to list matches.", 405)


@app.route("/api/matches/find")
@login_required
def api_matches_find():
    """
    GET /api/matches/find?surplus_id=<id>
    Run matching engine + nutrition enrichment and return ranked candidates.
    """
    surplus_id = request.args.get("surplus_id", "").strip()
    if not surplus_id:
        return _err("surplus_id is required.")

    surplus_rows = load_surplus_log()
    surplus_row  = next((r for r in surplus_rows if r.get("surplus_id") == surplus_id), None)
    if surplus_row is None:
        return _err(f"Surplus ID '{surplus_id}' not found.", 404)

    try:
        from models.matching_engine import make_surplus_record, load_ngo_records, match_ngos
        from models.nutrition_matcher import load_nutrition_db, enrich_matches

        surplus = make_surplus_record(
            kitchen_id=surplus_row.get("kitchen_id", ""),
            food_item=surplus_row.get("food_item", ""),
            quantity_kg=surplus_row.get("quantity_kg", 0),
            date_of_surplus=surplus_row.get("date_of_surplus", ""),
            expiry_time_hours=surplus_row.get("expiry_time_hours", 1),
            urgency=surplus_row.get("urgency", "medium"),
            surplus_id=surplus_id,
            status=surplus_row.get("status", "confirmed"),
        )

        ngo_list    = load_ngos()
        ngo_records = load_ngo_records(ngo_list)
        kitchens    = load_kitchens()

        base_matches = match_ngos(surplus, ngo_records, kitchens=kitchens)

        # Enrich with nutrition
        try:
            db = load_nutrition_db()
            enriched = enrich_matches(surplus.food_item, base_matches, db)
            matches_dicts = [m.to_dict() for m in enriched]
        except Exception as exc:
            logger.warning("Nutrition enrichment failed: %s", exc)
            matches_dicts = [m.to_dict() for m in base_matches]

        # Add surplus_id back for frontend "confirm" action
        for m in matches_dicts:
            m["surplus_id"] = surplus_id

        return _ok({"matches": matches_dicts, "surplus": surplus.to_dict()})

    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:
        logger.error("api_matches_find error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


@app.route("/api/matches/confirm", methods=["POST"])
@login_required
def api_matches_confirm():
    """
    POST /api/matches/confirm
    Body: { ngo_id, surplus_id, score?, distance_km?, quantity_kg? }
    Saves to matches.csv and sustainability_log.csv.
    """
    data = request.get_json(silent=True) or {}
    ngo_id     = data.get("ngo_id", "").strip()
    surplus_id = data.get("surplus_id", "").strip()

    if not ngo_id or not surplus_id:
        return _err("ngo_id and surplus_id are required.")

    # Find the surplus record
    surplus_rows = load_surplus_log()
    surplus_row  = next((r for r in surplus_rows if r.get("surplus_id") == surplus_id), None)
    if surplus_row is None:
        return _err(f"Surplus '{surplus_id}' not found.", 404)

    # Build match record
    match_id = "M" + str(uuid.uuid4())[:8].upper()
    match_record = {
        "match_id":    match_id,
        "surplus_id":  surplus_id,
        "kitchen_id":  surplus_row.get("kitchen_id", ""),
        "ngo_id":      ngo_id,
        "food_item":   surplus_row.get("food_item", ""),
        "quantity_kg": surplus_row.get("quantity_kg", 0),
        "distance_km": data.get("distance_km", ""),
        "score":       data.get("score", ""),
        "status":      "confirmed",
        "created_at":  _now_iso(),
    }

    rows = load_matches()
    rows.append(match_record)
    save_matches(rows)

    # Update surplus status
    for r in surplus_rows:
        if r.get("surplus_id") == surplus_id:
            r["status"] = "matched"
    save_surplus_log(surplus_rows)

    # Write to sustainability log
    _log_sustainability(
        kitchen_id=surplus_row.get("kitchen_id", ""),
        food_redistributed_kg=float(surplus_row.get("quantity_kg", 0) or 0),
        food_waste_avoided_kg=float(surplus_row.get("quantity_kg", 0) or 0),
    )

    return _ok({"message": "Match confirmed.", "match_id": match_id})


@app.route("/api/matches/<match_id>/status", methods=["PATCH"])
@login_required
def api_match_status(match_id):
    data   = request.get_json(silent=True) or {}
    status = data.get("status", "").strip().lower()
    if status not in ("accepted", "rejected", "pending", "confirmed", "completed"):
        return _err("Invalid status.")

    rows = load_matches()
    updated = False
    for r in rows:
        if r.get("match_id") == match_id:
            r["status"] = status
            updated = True
    if not updated:
        return _err(f"Match '{match_id}' not found.", 404)
    save_matches(rows)
    return _ok({"message": f"Match status updated to '{status}'."})


@app.route("/api/ngo/matches")
@login_required
def api_ngo_matches():
    """Return confirmed matches assigned to the current NGO user."""
    rows = load_matches()
    # If user is NGO, filter by their ngo_id derived from institution
    if session.get("role") == "ngo":
        institution = session.get("institution", "").strip().lower()
        ngos = load_ngos()
        ngo_id = None
        for n in ngos:
            if n.get("name", "").strip().lower() == institution:
                ngo_id = n.get("ngo_id")
                break
        if ngo_id:
            rows = [r for r in rows if r.get("ngo_id") == ngo_id]
    return _ok({"matches": rows})


# ===========================================================================
# API — ROUTE OPTIMIZATION (Feature 6)
# ===========================================================================

@app.route("/api/route")
@login_required
def api_route():
    """
    GET /api/route?surplus_id=<id>
    Returns an OptimizedRoute.to_dict() response.
    """
    surplus_id = request.args.get("surplus_id", "").strip()

    try:
        from models.route_optimizer import build_stops_from_matches, optimize_route

        kitchens = load_kitchens()

        # Build stops from confirmed matches for this surplus
        match_rows = load_matches()
        ngo_list   = load_ngos()
        ngo_lookup = {n.get("ngo_id"): n for n in ngo_list}

        # Determine the kitchen
        kitchen = None
        matched_ngos = []
        if surplus_id:
            relevant_matches = [
                r for r in match_rows if r.get("surplus_id") == surplus_id
            ]
            if relevant_matches:
                kid = relevant_matches[0].get("kitchen_id", "")
                kitchen = kitchens.get(kid)
                for m in relevant_matches:
                    ngo = ngo_lookup.get(m.get("ngo_id", ""))
                    if ngo:
                        matched_ngos.append(ngo)

        # Fall back: use the session user's kitchen + all active NGOs
        if kitchen is None:
            kid = _get_kitchen_id()
            kitchen = kitchens.get(kid, list(kitchens.values())[0] if kitchens else {})
        if not matched_ngos:
            matched_ngos = [n for n in ngo_list if n.get("status") == "active"][:5]

        if not kitchen:
            return _err("No kitchen data available for route optimisation.")

        # Build RouteStop objects directly from dicts
        from models.route_optimizer import build_stops_from_dicts, RouteStop
        stop_dicts = [{
            "stop_id":   kitchen.get("kitchen_id", "depot"),
            "name":      kitchen.get("name", "Kitchen"),
            "lat":       kitchen.get("lat"),
            "lon":       kitchen.get("lon"),
            "stop_type": "kitchen",
            "urgency":   "medium",
            "is_depot":  True,
        }]
        for ngo in matched_ngos:
            stop_dicts.append({
                "stop_id":   ngo.get("ngo_id", "ngo"),
                "name":      ngo.get("name", "NGO"),
                "lat":       ngo.get("lat"),
                "lon":       ngo.get("lon"),
                "stop_type": "ngo",
                "urgency":   "medium",
                "is_depot":  False,
            })

        stops = build_stops_from_dicts(stop_dicts)
        route = optimize_route(stops, urgency_first=True)
        return _ok(route.to_dict())

    except Exception as exc:
        logger.error("api_route error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


# ===========================================================================
# API — PRODUCTION PLANNING (Feature 7)
# ===========================================================================

@app.route("/api/production_planning")
@login_required
def api_production_planning():
    try:
        from models.production_planner import generate_recommendations
        result = generate_recommendations()
        return _ok(result)
    except Exception as exc:
        logger.error("api_production_planning error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


# ===========================================================================
# API — SUSTAINABILITY ANALYTICS (Feature 8)
# ===========================================================================

@app.route("/api/sustainability")
@login_required
def api_sustainability():
    try:
        from models.sustainability_calc import calculate_metrics
        result = calculate_metrics()
        return _ok(result)
    except Exception as exc:
        logger.error("api_sustainability error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


@app.route("/api/sustainability/trend")
@login_required
def api_sustainability_trend():
    try:
        from models.sustainability_calc import get_sustainability_trend
        result = get_sustainability_trend()
        return _ok(result)
    except Exception as exc:
        logger.error("api_sustainability_trend error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


@app.route("/api/sustainability/by-kitchen")
@login_required
def api_sustainability_by_kitchen():
    try:
        from models.sustainability_calc import aggregate_by_kitchen
        result = aggregate_by_kitchen()
        return _ok(result)
    except Exception as exc:
        logger.error("api_sustainability_by_kitchen error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


# ===========================================================================
# API — ESG / CSR REPORT (Feature 9)
# ===========================================================================

@app.route("/api/report/download", methods=["POST"])
@login_required
def api_report_download():
    """
    POST /api/report/download
    Body: { institution_name, reporting_period_start, reporting_period_end }
    Generates a PDF and returns a download URL.
    """
    data = request.get_json(silent=True) or {}
    institution = data.get("institution_name") or session.get("institution", "Institution")
    period_start = data.get("reporting_period_start", "")
    period_end   = data.get("reporting_period_end", "")

    try:
        from models.sustainability_calc import calculate_metrics, get_sustainability_trend, aggregate_by_date
        from models.production_planner import generate_recommendations
        from models.report_generator import generate_report

        metrics = calculate_metrics()
        trend   = get_sustainability_trend()
        recs    = generate_recommendations()

        report_data = {
            "institution_name":                institution,
            "reporting_period_start":          period_start,
            "reporting_period_end":            period_end,
            "food_redistributed_kg":           metrics.get("total_food_redistributed_kg", 0),
            "food_waste_avoided_kg":           metrics.get("total_food_waste_avoided_kg", 0),
            "meals_redistributed":             metrics.get("total_meals_redistributed", 0),
            "estimated_co2e_avoided_kg":       metrics.get("estimated_co2e_avoided_kg", 0),
            "estimated_water_saved_liters":    metrics.get("estimated_water_saved_liters", 0),
            "sustainability_trend":            trend.get("daily_series", [])[:20],
            "donation_records":                load_matches()[:30],
            "production_planning_recommendations": recs.get("recommendations", [])[:5],
        }

        pdf_path = generate_report(report_data)
        pdf_filename = Path(pdf_path).name

        return _ok({
            "message":      "Report generated successfully.",
            "download_url": url_for("download_report", filename=pdf_filename),
            "filename":     pdf_filename,
        })

    except ImportError as exc:
        return _err(f"Report generation unavailable: {exc}", 503)
    except Exception as exc:
        logger.error("api_report_download error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


@app.route("/reports/<path:filename>")
@login_required
def download_report(filename):
    """Serve generated PDF reports."""
    reports_dir = config.REPORTS_DIR
    file_path = reports_dir / filename
    if not file_path.exists():
        return _err("Report file not found.", 404)
    return send_file(str(file_path), as_attachment=True, download_name=filename)


# ===========================================================================
# API — RAW MATERIAL EXCHANGE (Feature 3)
# ===========================================================================

@app.route("/api/exchange/listing", methods=["POST"])
@login_required
def api_exchange_listing():
    """POST — create a raw material listing."""
    data = request.get_json(silent=True) or {}
    try:
        from utils.validators import (
            validate_ingredient, validate_quantity,
            validate_unit, validate_date_str, validate_use_by_date,
        )
        ingredient  = validate_ingredient(data.get("ingredient", ""))
        quantity    = validate_quantity(data.get("quantity", 0))
        unit        = validate_unit(data.get("unit", "kg"))
        date_listed = validate_date_str(data.get("date_listed", ""))
        use_by      = validate_use_by_date(data.get("use_by_date") or None)

        listing_id  = "L" + str(uuid.uuid4())[:8].upper()
        kitchen_id  = _get_kitchen_id()

        record = {
            "listing_id":  listing_id,
            "kitchen_id":  kitchen_id,
            "ingredient":  ingredient,
            "quantity":    str(quantity),
            "unit":        unit,
            "date_listed": str(date_listed),
            "use_by_date": str(use_by) if use_by else "",
            "status":      "AVAILABLE",
        }
        rows = load_raw_material_log()
        rows.append(record)
        save_raw_material_log(rows)
        return _ok({"message": "Material listed.", "listing_id": listing_id})

    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:
        logger.error("api_exchange_listing error: %s", exc, exc_info=True)
        return _err(str(exc), 500)


@app.route("/api/exchange/listings")
@login_required
def api_exchange_listings():
    """Return current user's listings."""
    rows = load_raw_material_log()
    if session.get("role") == "kitchen":
        kid = _get_kitchen_id()
        rows = [r for r in rows if r.get("kitchen_id") == kid]
    return _ok({"listings": rows})


@app.route("/api/exchange/matches")
@login_required
def api_exchange_matches():
    """
    GET /api/exchange/matches?ingredient=&quantity=&date=&urgency=
    Find available listings matching the request.
    """
    ingredient_need = (request.args.get("ingredient") or "").strip().lower()
    qty_need_raw    = request.args.get("quantity", "0")
    urgency         = request.args.get("urgency", "medium")

    try:
        qty_need = float(qty_need_raw) if qty_need_raw else 0.0
    except ValueError:
        qty_need = 0.0

    rows = load_raw_material_log()
    kid  = _get_kitchen_id()
    kitchens = load_kitchens()

    results = []
    for r in rows:
        if r.get("kitchen_id") == kid:
            continue  # skip own listings
        if r.get("status", "").upper() != "AVAILABLE":
            continue
        listing_ingredient = r.get("ingredient", "").strip().lower()
        if ingredient_need and ingredient_need not in listing_ingredient and listing_ingredient not in ingredient_need:
            continue

        # Calculate simple score based on quantity match + distance
        try:
            avail_qty = float(r.get("quantity", 0))
        except (ValueError, TypeError):
            avail_qty = 0.0

        qty_score = min(avail_qty / qty_need, 1.0) if qty_need > 0 else 1.0

        # Distance score
        offering_kitchen = kitchens.get(r.get("kitchen_id", ""), {})
        my_kitchen = kitchens.get(kid, {})
        dist_km = None
        try:
            from utils.distance import haversine_km
            if all(k in offering_kitchen and k in my_kitchen for k in ("lat", "lon")):
                dist_km = haversine_km(
                    float(my_kitchen["lat"]), float(my_kitchen["lon"]),
                    float(offering_kitchen["lat"]), float(offering_kitchen["lon"]),
                )
        except Exception:
            pass

        dist_score = (1.0 - dist_km / 100.0) if dist_km is not None else 0.5
        dist_score = max(0.0, min(1.0, dist_score))
        score = round(0.6 * qty_score + 0.4 * dist_score, 4)

        reasons = [
            f"Ingredient match: {r.get('ingredient')}",
            f"Available: {avail_qty} {r.get('unit', 'kg')}",
        ]
        if dist_km is not None:
            reasons.append(f"Distance: {dist_km:.1f} km")

        results.append({
            "listing": r,
            "score":   score,
            "distance_km": round(dist_km, 2) if dist_km is not None else None,
            "reasons": reasons,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return _ok({"matches": results[:10]})


@app.route("/api/exchange/propose", methods=["POST"])
@login_required
def api_exchange_propose():
    """Record an exchange proposal."""
    data = request.get_json(silent=True) or {}
    listing_id = data.get("listing_id", "").strip()
    if not listing_id:
        return _err("listing_id is required.")

    rows = load_raw_material_log()
    listing = next((r for r in rows if r.get("listing_id") == listing_id), None)
    if listing is None:
        return _err(f"Listing '{listing_id}' not found.", 404)

    exchange_id = "E" + str(uuid.uuid4())[:8].upper()
    exchange = {
        "exchange_id":          exchange_id,
        "listing_id":           listing_id,
        "offering_kitchen_id":  listing.get("kitchen_id", ""),
        "requesting_kitchen_id": _get_kitchen_id(),
        "ingredient":           listing.get("ingredient", ""),
        "offered_quantity":     listing.get("quantity", ""),
        "requested_quantity":   data.get("requested_quantity", listing.get("quantity", "")),
        "unit":                 listing.get("unit", "kg"),
        "status":               "proposed",
        "created_at":           _now_iso(),
        "updated_at":           _now_iso(),
    }
    ex_rows = load_exchange_log()
    ex_rows.append(exchange)
    save_exchange_log(ex_rows)

    # Update listing status
    for r in rows:
        if r.get("listing_id") == listing_id:
            r["status"] = "PENDING"
    save_raw_material_log(rows)

    return _ok({"message": "Exchange proposed.", "exchange_id": exchange_id})


@app.route("/api/exchange/mine")
@login_required
def api_exchange_mine():
    """Return exchanges involving the current kitchen."""
    kid = _get_kitchen_id()
    rows = load_exchange_log()
    mine = [
        r for r in rows
        if r.get("offering_kitchen_id") == kid or r.get("requesting_kitchen_id") == kid
    ]
    return _ok({"exchanges": mine})


# ===========================================================================
# API — ADMIN (Feature: admin dashboard)
# ===========================================================================

@app.route("/api/kitchens")
@login_required
def api_kitchens():
    kitchens = load_kitchens()
    kitchen_list = list(kitchens.values())
    return _ok({"kitchens": kitchen_list})


@app.route("/api/ngos")
@login_required
def api_ngos():
    ngos = load_ngos()
    return _ok({"ngos": ngos})


# ===========================================================================
# Sustainability log helper (internal)
# ===========================================================================

def _log_sustainability(
    kitchen_id: str,
    food_redistributed_kg: float,
    food_waste_avoided_kg: float,
    meals_count: int = 0,
):
    """Append a row to sustainability_log.csv."""
    import csv
    log_file = config.SUSTAINABILITY_LOG_FILE
    file_exists = log_file.exists()
    fieldnames = [
        "kitchen_id", "date", "food_redistributed_kg",
        "food_waste_avoided_kg", "meals_count",
    ]
    with open(log_file, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists or log_file.stat().st_size == 0:
            writer.writeheader()
        writer.writerow({
            "kitchen_id":             kitchen_id,
            "date":                   datetime.now().strftime("%Y-%m-%d"),
            "food_redistributed_kg":  round(food_redistributed_kg, 4),
            "food_waste_avoided_kg":  round(food_waste_avoided_kg, 4),
            "meals_count":            meals_count,
        })


# ===========================================================================
# Error handlers
# ===========================================================================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return _err("Endpoint not found.", 404)
    return redirect(url_for("auth.login"))


@app.errorhandler(500)
def server_error(e):
    logger.error("Unhandled 500: %s", e)
    if request.path.startswith("/api/"):
        return _err("Internal server error.", 500)
    return render_template("login.html"), 500


# ===========================================================================
# Startup: train demand model in background
# ===========================================================================

def _start_background_training():
    """Kick off demand model training in a daemon thread."""
    t = threading.Thread(target=_load_demand_model, daemon=True, name="demand-trainer")
    t.start()
    logger.info("Demand model training started in background thread.")


# ===========================================================================
# Entrypoint
# ===========================================================================

if __name__ == "__main__":
    _start_background_training()
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
