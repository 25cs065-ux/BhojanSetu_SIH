# 🍲 BhojanSetu

**AI-Powered Smart Food Waste Reduction and Sustainable Redistribution Ecosystem for Institutional Kitchens and Food Processing Units**

Built for **Smart India Hackathon 2026** — Problem Statement **SIH26234**
Theme: Agriculture, FoodTech & Rural Development | Category: Software

> BhojanSetu doesn't just redistribute food waste after it happens — it prevents it, one stage earlier, at the point of procurement.

---

## 🌟 What makes BhojanSetu different

Most food-waste platforms act *after* a meal is cooked. BhojanSetu acts at three stages:

1. **Procurement stage (our key innovation)** — Kitchens list excess raw ingredients before they're ever cooked, and the system matches them with nearby kitchens that need exactly that ingredient — kitchen-to-kitchen, before a single grain is prepared.
2. **Kitchen stage** — AI-powered demand forecasting and surplus prediction, with a fully explainable AI panel showing *why* a prediction was made.
3. **Redistribution stage** — Nutrition-aware, AI-ranked NGO matching with route-optimized pickup, feeding straight into live sustainability analytics and one-click ESG/CSR report generation.

## ✨ Features

| # | Feature | Description |
|---|---|---|
| 1 | AI Demand Forecasting | Predicts required food quantity from historical consumption data |
| 2 | Surplus Prediction | Flags expected leftover food before overproduction happens |
| 3 | **Pre-Production Raw Material Exchange** | Kitchen-to-kitchen exchange of excess raw ingredients, before cooking |
| 4 | AI-Based NGO Matching | Matches surplus to NGOs by quantity, urgency, distance, and capacity |
| 5 | Nutrition-Aware Matching | Refines NGO matches using nutritional profile data |
| 6 | Route Optimization | Efficient pickup/delivery sequencing, mapped with Leaflet + OpenStreetMap |
| 7 | Data-Driven Production Planning | Purchasing/preparation recommendations from historical waste patterns |
| 8 | Sustainability Analytics | Tracks waste prevented, CO2e avoided, meals redistributed |
| 9 | ESG / CSR Report Generation | One-click, auto-generated PDF reports for compliance |
| 10 | Explainable AI | Shows the top factors behind every AI prediction |

## 🛠️ Tech Stack

- **Backend:** Python, Flask
- **AI / ML:** scikit-learn (Random Forest demand forecasting), pandas, numpy
- **Frontend:** HTML, CSS, vanilla JavaScript (no frameworks)
- **Maps:** Leaflet.js + OpenStreetMap
- **Reports:** ReportLab (PDF generation)
- **Data:** JSON/CSV flat-file storage for application data + public Kaggle datasets for training/reference

## 📁 Project Structure

```
BhojanSetu/
├── app.py                  # Flask entry point
├── config.py                # Central path/config
├── requirements.txt
├── seed_admin.py             # Creates a demo admin account
├── auth/                   # Login, signup, OTP verification
├── models/                  # AI/ML modules (forecasting, matching, routing, planning, reports)
├── data/                    # Application-generated data (JSON/CSV)
├── datasets/                # Kaggle source datasets (read-only)
├── templates/                # HTML pages
├── static/                  # CSS, JS, images
├── tests/                   # Test suite
└── reports/                 # Generated ESG/CSR PDF reports
```

## 🚀 How to Run

**1. Clone the repository**
```bash
git clone https://github.com/25cs065-ux/BhojanSetu_SIH
cd BhojanSetu
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Seed a demo admin account** (one-time)
```bash
python seed_admin.py
```

**5. Run the app**
```bash
python app.py
```
Wait for the terminal to show `Demand forecasting model trained and ready.` (~60–90 seconds on first start), then open:

```
(paste this in your browser)

http://127.0.0.1:5000
```

### Demo logins

| Role | Email | Password |
|---|---|---|
| Admin | `admin@bhojansetu.local` | `Admin@1234` |
| Kitchen / NGO | Sign up fresh from the app — an OTP is shown on-screen after signup (demo mode, no real email sent) | — |

## 👥 Team — RightRangers

| Member | Role | Contribution |
|---|---|---|
| Khushi Patel| Team Lead / Integration Engineer | Authentication system, Flask app integration, connecting all modules end-to-end |
| Siddhi Panchal | AI Engineer | Demand forecasting model, surplus prediction engine |
| Zeel Patel | AI Engineer | NGO matching engine, nutrition-aware matching, route optimization |
| Seena Patel | AI Engineer | Production planning, sustainability analytics, ESG report generation, explainable AI |
| Aadya | Frontend Developer | All UI templates, dashboards, client-side JavaScript |
| Nandani Patel | Data Engineer | Application data layer, dataset integration, validation utilities |


## 📊 Datasets Used

| File | Source | Key columns used |
|---|---|---|
| `food_demand_history.csv` | Kaggle — "Food Demand Forecasting" (Genpact hackathon dataset): `train.csv`, `meal_info.csv`, `fulfilment_center_info.csv`, merged | Weekly `num_orders` per meal per center, price, promotion flags — drives demand forecasting |
| `food_demand_history.csv` (surplus-focused) | Kaggle — "Food Wastage Restaurant" / "Canteen Food Waste" / "Global Food Wastage Dataset" | Date, food item, quantity prepared, quantity wasted/sold — feeds `surplus_predictor.py` |
| `recipe_nutrition.csv` | Kaggle — "Indian Food Nutrition" / "Indian Food Composition Table" / "Indian Food 101" | Calories, protein, carbs, fat, fibre per 100g, plus ingredients — used for nutrition-aware NGO matching |
| `emission_factors.csv` | Our World in Data (Poore & Nemecek, *Environmental Impact of Food Production*) | kg CO₂e per kg of food, water use per kg — used in sustainability analytics and ESG reports |

## 📄 License

Built for Smart India Hackathon 2026. All rights reserved by Team RightRangers.
