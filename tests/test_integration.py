"""
Integration smoke tests for BhojanSetu.
Run with:  python test_integration.py
"""
import sys, os
sys.path.insert(0, '.')

print("=" * 60)
print("BhojanSetu Integration Smoke Tests")
print("=" * 60)

failures = []

def test(name, fn):
    try:
        result = fn()
        print(f"  PASS  {name}")
        return result
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        failures.append((name, e))
        return None

# -------------------------------------------------------------------
# 1. Config paths
# -------------------------------------------------------------------
print("\n[1] Configuration")
import config
test("PROJECT_ROOT exists", lambda: config.PROJECT_ROOT.exists())
test("DATA_DIR exists", lambda: config.DATA_DIR.exists())
test("DATASET_DIR exists", lambda: config.DATASET_DIR.exists())
test("train.csv present", lambda: config.TRAIN_CSV.exists())
test("meal_info.csv present", lambda: config.MEAL_INFO_CSV.exists())
test("fulfilment_center_info.csv present", lambda: config.FULFILMENT_CENTER_INFO_CSV.exists())

# -------------------------------------------------------------------
# 2. Data layer
# -------------------------------------------------------------------
print("\n[2] Data Layer")
from utils.data_loader import load_kitchens, load_ngos, load_surplus_log, load_matches

kitchens = test("load_kitchens()", load_kitchens)
ngos = test("load_ngos()", load_ngos)
surplus = test("load_surplus_log()", load_surplus_log)
matches = test("load_matches()", load_matches)

test("kitchens is dict", lambda: isinstance(kitchens, dict))
test("kitchens has 5 entries", lambda: len(kitchens) == 5)
test("ngos is list", lambda: isinstance(ngos, list))
test("ngos has 5 entries", lambda: len(ngos) == 5)

# -------------------------------------------------------------------
# 3. Auth utils
# -------------------------------------------------------------------
print("\n[3] Auth Utils")
from auth.utils import create_user, verify_credentials, generate_otp, verify_otp

# Clean up test user
import json
from pathlib import Path
users_file = Path('data/users.json')
orig = users_file.read_text()

test("create_user()", lambda: create_user(
    email='test@example.com', password='test1234pass',
    full_name='Test User', role='kitchen', institution='Test Kitchen'
))
test("verify_credentials() correct", lambda: verify_credentials('test@example.com', 'test1234pass') is not None)
test("verify_credentials() wrong password", lambda: verify_credentials('test@example.com', 'wrongpass') is None)
otp = test("generate_otp()", lambda: generate_otp('test@example.com'))
test("verify_otp() correct", lambda: verify_otp('test@example.com', otp))
test("verify_otp() incorrect", lambda: not verify_otp('test@example.com', '000000'))

# Restore users.json
users_file.write_text(orig)

# -------------------------------------------------------------------
# 4. Validators
# -------------------------------------------------------------------
print("\n[4] Validators")
from utils.validators import validate_ingredient, validate_quantity, validate_unit, validate_urgency, validate_date_str

test("validate_ingredient('Rice')", lambda: validate_ingredient('Rice') == 'Rice')
test("validate_quantity(10.5)", lambda: validate_quantity(10.5) == 10.5)
test("validate_unit('kg')", lambda: validate_unit('kg') == 'kg')
test("validate_urgency('high')", lambda: validate_urgency('high') == 'high')
test("validate_date_str('2025-01-15')", lambda: validate_date_str('2025-01-15'))
try:
    validate_quantity(-1)
    failures.append(("validate_quantity(-1) should raise", "No exception raised"))
    print("  FAIL  validate_quantity(-1) should raise ValueError")
except ValueError:
    print("  PASS  validate_quantity(-1) raises ValueError")

# -------------------------------------------------------------------
# 5. Distance
# -------------------------------------------------------------------
print("\n[5] Distance")
from utils.distance import haversine_km
dist = test("haversine_km IIT Delhi -> AIIMS", lambda: haversine_km(28.545, 77.1926, 28.5672, 77.2100))
test("haversine_km is positive float", lambda: dist > 0)
test("haversine_km IIT->AIIMS approx 3km", lambda: 1 < dist < 8)

# -------------------------------------------------------------------
# 6. Surplus Predictor
# -------------------------------------------------------------------
print("\n[6] Surplus Predictor")
from models.surplus_predictor import SurplusPredictor
sp = SurplusPredictor()
result = test("sp.calculate(100, 82)", lambda: sp.calculate(prepared_qty=100, forecast_demand=82, item_name='Rice'))
test("surplus ~18", lambda: abs(result['estimated_surplus'] - 18.0) < 0.1)
test("risk_level is MEDIUM", lambda: result['risk_level'] == 'MEDIUM')
test("sp.classify_risk(5) == LOW", lambda: sp.classify_risk(5) == 'LOW')
test("sp.classify_risk(-3) == SHORTAGE", lambda: sp.classify_risk(-3) == 'SHORTAGE')
test("sp.classify_risk(30) == HIGH", lambda: sp.classify_risk(30) == 'HIGH')

# -------------------------------------------------------------------
# 7. Matching Engine
# -------------------------------------------------------------------
print("\n[7] Matching Engine")
from models.matching_engine import make_surplus_record, load_ngo_records, match_ngos

surplus_rec = test("make_surplus_record()", lambda: make_surplus_record(
    kitchen_id='K001', food_item='Dal Rice', quantity_kg=50,
    date_of_surplus='2025-06-01', expiry_time_hours=6, urgency='high'
))
ngo_records = test("load_ngo_records()", lambda: load_ngo_records(ngos))
test("ngo_records length >=4 active", lambda: len(ngo_records) >= 4)

from utils.data_loader import load_kitchens as lk
matches_found = test("match_ngos()", lambda: match_ngos(surplus_rec, ngo_records, kitchens=lk()))
test("at least 1 match found", lambda: len(matches_found) >= 1)
test("matches sorted by score desc", lambda: all(
    matches_found[i].score >= matches_found[i+1].score
    for i in range(len(matches_found)-1)
))

# -------------------------------------------------------------------
# 8. Nutrition Matcher
# -------------------------------------------------------------------
print("\n[8] Nutrition Matcher")
from models.nutrition_matcher import load_nutrition_db, get_nutrition_profile, nutrition_score, enrich_matches

db = test("load_nutrition_db()", load_nutrition_db)
test("db.size() > 0", lambda: db.size() > 0)
print(f"      Nutrition DB size: {db.size()} entries")
profile = test("get_nutrition_profile('dal')", lambda: get_nutrition_profile('dal', db))
enriched = test("enrich_matches()", lambda: enrich_matches('Dal Rice', matches_found, db))
test("enriched has adjusted_score", lambda: all(hasattr(m, 'adjusted_score') for m in enriched))

# -------------------------------------------------------------------
# 9. Route Optimizer
# -------------------------------------------------------------------
print("\n[9] Route Optimizer")
from models.route_optimizer import build_stops_from_dicts, optimize_route

stops = test("build_stops_from_dicts()", lambda: build_stops_from_dicts([
    {"stop_id": "K001", "name": "IIT Delhi", "lat": 28.545, "lon": 77.1926, "stop_type": "kitchen", "is_depot": True},
    {"stop_id": "N001", "name": "Feeding India", "lat": 28.652, "lon": 77.19, "stop_type": "ngo"},
    {"stop_id": "N002", "name": "Delhi Food Bank", "lat": 28.57, "lon": 77.24, "stop_type": "ngo"},
]))
route = test("optimize_route()", lambda: optimize_route(stops))
test("route.total_km > 0", lambda: route.total_km > 0)
test("route has 3 stops", lambda: len(route.stops) == 3)
route_dict = test("route.to_dict()", lambda: route.to_dict())

# -------------------------------------------------------------------
# 10. Production Planner
# -------------------------------------------------------------------
print("\n[10] Production Planner")
from models.production_planner import generate_recommendations

plan = test("generate_recommendations() no data", generate_recommendations)
test("plan has status key", lambda: 'metadata' in plan)
test("plan has recommendations list", lambda: 'recommendations' in plan)

# With some test records
test_surplus = [
    {"food_item": "Rice", "quantity_kg": "10", "date": "2025-01-01"},
    {"food_item": "Rice", "quantity_kg": "8",  "date": "2025-01-08"},
    {"food_item": "Rice", "quantity_kg": "12", "date": "2025-01-15"},
]
plan2 = test("generate_recommendations(test_data)", lambda: generate_recommendations(
    surplus_records=test_surplus, min_occurrences=2
))
test("plan2 has Rice recommendation", lambda: len(plan2['recommendations']) >= 1)

# -------------------------------------------------------------------
# 11. Sustainability Calculator
# -------------------------------------------------------------------
print("\n[11] Sustainability Calculator")
from models.sustainability_calc import calculate_metrics, aggregate_by_date, get_sustainability_trend

# With test data
test_activity = [
    {"kitchen_id": "K001", "date": "2025-01-01", "food_redistributed_kg": "20", "food_waste_avoided_kg": "15"},
    {"kitchen_id": "K001", "date": "2025-01-02", "food_redistributed_kg": "10", "food_waste_avoided_kg": "10"},
]
metrics = test("calculate_metrics(test_data)", lambda: calculate_metrics(test_activity))
test("metrics.status == ok", lambda: metrics['status'] == 'ok')
test("total_redistributed == 30", lambda: metrics['total_food_redistributed_kg'] == 30.0)
test("co2e_avoided > 0", lambda: metrics['estimated_co2e_avoided_kg'] > 0)
daily = test("aggregate_by_date()", lambda: aggregate_by_date(test_activity))
test("daily has 2 entries", lambda: len(daily) == 2)
trend = test("get_sustainability_trend()", lambda: get_sustainability_trend(test_activity))
test("trend has daily_series", lambda: 'daily_series' in trend)

# -------------------------------------------------------------------
# 12. Report Generator
# -------------------------------------------------------------------
print("\n[12] Report Generator")
from models.report_generator import generate_report, REPORTLAB_AVAILABLE
import tempfile, os

test("REPORTLAB_AVAILABLE is True", lambda: REPORTLAB_AVAILABLE is True)
if REPORTLAB_AVAILABLE:
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        path = test("generate_report()", lambda: generate_report({
            "institution_name": "Test Kitchen",
            "reporting_period_start": "2025-01-01",
            "reporting_period_end": "2025-01-31",
            "food_redistributed_kg": 30.0,
            "food_waste_avoided_kg": 25.0,
            "meals_redistributed": 60,
            "estimated_co2e_avoided_kg": 40.0,
            "estimated_water_saved_liters": 10000.0,
        }, output_path=tmp_path))
        test("PDF file created", lambda: os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000)
        os.unlink(tmp_path)
    except Exception as e:
        print(f"  FAIL  generate_report: {e}")
        failures.append(("generate_report", e))

# -------------------------------------------------------------------
# 13. Explainability
# -------------------------------------------------------------------
print("\n[13] Explainability")
from models.explainability import explain_prediction
from sklearn.ensemble import RandomForestRegressor
import numpy as np

# Train a tiny RF for testing
X = np.random.rand(50, 3)
y = np.random.rand(50)
model = RandomForestRegressor(n_estimators=5, random_state=42)
model.fit(X, y)

expl = test("explain_prediction(RF model)", lambda: explain_prediction(
    model=model, feature_names=['feat_a', 'feat_b', 'feat_c']
))
test("explainable is True", lambda: expl['explainable'] is True)
test("has ranked_factors", lambda: len(expl['ranked_factors']) == 3)
test("method == feature_importances", lambda: expl['method'] == 'feature_importances')

# None model
expl_none = test("explain_prediction(None)", lambda: explain_prediction(model=None))
test("explainable False for None", lambda: expl_none['explainable'] is False)

# -------------------------------------------------------------------
# 14. Flask app routes
# -------------------------------------------------------------------
print("\n[14] Flask App Routes")
import app as flask_app
client = flask_app.app.test_client()

resp = test("GET / redirects", lambda: client.get('/'))
test("GET / -> 302", lambda: resp.status_code == 302)

resp = test("GET /auth/login", lambda: client.get('/auth/login'))
test("login page returns 200", lambda: resp.status_code == 200)
test("login page has BhojanSetu", lambda: b'BhojanSetu' in resp.data)

resp = test("GET /auth/signup", lambda: client.get('/auth/signup'))
test("signup page returns 200", lambda: resp.status_code == 200)

# Protected routes should redirect to login
resp = test("GET /dashboard/kitchen unauth", lambda: client.get('/dashboard/kitchen'))
test("dashboard redirects when unauth", lambda: resp.status_code == 302)

resp = test("GET /api/surplus unauth", lambda: client.get('/api/surplus'))
test("API redirects when unauth", lambda: resp.status_code in (302, 401))

# -------------------------------------------------------------------
# 15. Flask app with session (authenticated requests)
# -------------------------------------------------------------------
print("\n[15] Authenticated API Tests")
with flask_app.app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id']     = 'U0001'
        sess['user_name']   = 'Test User'
        sess['role']        = 'kitchen'
        sess['institution'] = 'IIT Delhi Central Kitchen'
        sess['email']       = 'test@example.com'

    resp = test("GET /dashboard/kitchen auth", lambda: c.get('/dashboard/kitchen'))
    test("kitchen dashboard returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/surplus auth", lambda: c.get('/api/surplus'))
    test("api/surplus returns 200", lambda: resp.status_code == 200)

    import json
    data = test("api/surplus JSON", lambda: json.loads(resp.data))
    test("api/surplus has items key", lambda: 'items' in data)

    resp = test("GET /api/kitchens", lambda: c.get('/api/kitchens'))
    test("api/kitchens returns 200", lambda: resp.status_code == 200)
    kitchens_data = json.loads(resp.data)
    test("api/kitchens has 5 kitchens", lambda: len(kitchens_data['kitchens']) == 5)

    resp = test("GET /api/ngos", lambda: c.get('/api/ngos'))
    test("api/ngos returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/sustainability", lambda: c.get('/api/sustainability'))
    test("api/sustainability returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/production_planning", lambda: c.get('/api/production_planning'))
    test("api/production_planning returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/route", lambda: c.get('/api/route'))
    test("api/route returns 200", lambda: resp.status_code == 200)

    # POST surplus
    resp = test("POST /api/surplus", lambda: c.post('/api/surplus',
        data=json.dumps({
            "food_item": "Dal Rice",
            "quantity_kg": 25.0,
            "date_of_surplus": "2025-06-01",
            "expiry_time_hours": 6.0,
            "urgency": "high"
        }),
        content_type='application/json'
    ))
    test("POST /api/surplus returns 200", lambda: resp.status_code == 200)
    surplus_resp = json.loads(resp.data)
    test("surplus logged with ID", lambda: 'surplus_id' in surplus_resp)
    surplus_id = surplus_resp.get('surplus_id', '')

    # GET surplus again to confirm logged
    resp = test("GET /api/surplus after log", lambda: c.get('/api/surplus'))
    data2 = json.loads(resp.data)
    test("surplus appears in log", lambda: len(data2['items']) >= 1)

    # Find matches for the surplus
    if surplus_id:
        resp = test("GET /api/matches/find", lambda: c.get(f'/api/matches/find?surplus_id={surplus_id}'))
        test("api/matches/find returns 200", lambda: resp.status_code == 200)
        match_data = json.loads(resp.data)
        test("matches returned", lambda: 'matches' in match_data)
        test("at least 1 match", lambda: len(match_data.get('matches', [])) >= 1)

        # Confirm a match
        if match_data.get('matches'):
            first_match = match_data['matches'][0]
            resp = test("POST /api/matches/confirm", lambda: c.post('/api/matches/confirm',
                data=json.dumps({
                    "ngo_id": first_match.get('ngo_id', 'N001'),
                    "surplus_id": surplus_id,
                    "score": first_match.get('score', 0.5),
                }),
                content_type='application/json'
            ))
            test("confirm match returns 200", lambda: resp.status_code == 200)

    # POST exchange listing
    from datetime import date
    resp = test("POST /api/exchange/listing", lambda: c.post('/api/exchange/listing',
        data=json.dumps({
            "ingredient": "Rice",
            "quantity": 20,
            "unit": "kg",
            "date_listed": str(date.today()),
        }),
        content_type='application/json'
    ))
    test("exchange listing returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/exchange/listings", lambda: c.get('/api/exchange/listings'))
    test("exchange listings returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/sustainability/trend", lambda: c.get('/api/sustainability/trend'))
    test("sustainability/trend returns 200", lambda: resp.status_code == 200)

    resp = test("GET /api/sustainability/by-kitchen", lambda: c.get('/api/sustainability/by-kitchen'))
    test("sustainability/by-kitchen returns 200", lambda: resp.status_code == 200)

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} test(s)")
    for name, err in failures:
        print(f"  - {name}: {err}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
