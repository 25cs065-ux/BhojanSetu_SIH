/* ============================================================
   BhojanSetu — charts.js
   Chart rendering helpers using Chart.js 4.
   All functions accept null/undefined data gracefully.
   No data is fabricated; charts only render received API data.
   ============================================================ */

'use strict';

/* ── Palette ─────────────────────────────────────────────── */
const BRAND   = '#1a5276';
const BRAND_L = '#2e86c1';
const GREEN   = '#1e8449';
const AMBER   = '#d68910';
const RED     = '#c0392b';
const MUTED   = '#909eac';
const SUBTLE  = '#d6eaf8';

/* ── Shared Chart.js defaults ────────────────────────────── */
Chart.defaults.font.family = '-apple-system,"Segoe UI",system-ui,sans-serif';
Chart.defaults.font.size   = 12;
Chart.defaults.color       = '#5d6d7e';

const _chartInstances = {};

function _destroyExisting(canvasId) {
  if (_chartInstances[canvasId]) {
    _chartInstances[canvasId].destroy();
    delete _chartInstances[canvasId];
  }
}

/* ─────────────────────────────────────────────────────────
   Feature 1 — Demand Forecast Chart
   Expects data: array of { week, predicted_demand,
                             lower_bound, upper_bound }
   from DemandForecaster.predict()
   ───────────────────────────────────────────────────────── */
function renderDemandChart(canvasId, data) {
  _destroyExisting(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (!data || data.length === 0) {
    canvas.parentElement.innerHTML =
      '<div class="chart-placeholder">No forecast data available.</div>';
    return;
  }

  const labels  = data.map(d => 'Week ' + d.week);
  const demand  = data.map(d => d.predicted_demand);
  const lower   = data.map(d => d.lower_bound  ?? null);
  const upper   = data.map(d => d.upper_bound  ?? null);

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Predicted Demand',
          data: demand,
          borderColor: BRAND,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
          order: 1,
        },
        {
          label: 'Upper Bound (95%)',
          data: upper,
          borderColor: 'transparent',
          backgroundColor: 'rgba(26,82,118,.10)',
          fill: '+1',
          pointRadius: 0,
          order: 2,
        },
        {
          label: 'Lower Bound (95%)',
          data: lower,
          borderColor: 'transparent',
          backgroundColor: 'rgba(26,82,118,.10)',
          fill: false,
          pointRadius: 0,
          order: 3,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top' },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.datasetIndex === 0)
                return `Predicted: ${ctx.parsed.y.toFixed(1)}`;
              if (ctx.datasetIndex === 1)
                return `Upper 95%: ${ctx.parsed.y?.toFixed(1) ?? 'N/A'}`;
              return `Lower 95%: ${ctx.parsed.y?.toFixed(1) ?? 'N/A'}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { color: '#edf1f5' } },
        y: { beginAtZero: false, grid: { color: '#edf1f5' } },
      },
    },
  });
}

/* ─────────────────────────────────────────────────────────
   Feature 2 — Surplus Risk Bar Chart
   Expects data: array of { item_name, surplus_pct, risk_level }
   from SurplusPredictor.batch_calculate()
   ───────────────────────────────────────────────────────── */
function renderSurplusRiskChart(canvasId, data) {
  _destroyExisting(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (!data || data.length === 0) {
    canvas.parentElement.innerHTML =
      '<div class="chart-placeholder">No surplus data available.</div>';
    return;
  }

  const riskColor = r => ({
    LOW: GREEN, MEDIUM: AMBER, HIGH: RED, SHORTAGE: '#7d3c98',
  })[r] || MUTED;

  const labels = data.map(d => d.item_name || String(d.meal_id || 'Item'));
  const values = data.map(d => d.surplus_pct ?? 0);
  const colors = data.map(d => riskColor(d.risk_level));

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Surplus %',
        data: values,
        backgroundColor: colors,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          title: { display: true, text: 'Surplus (%)' },
          grid: { color: '#edf1f5' },
        },
        y: { grid: { display: false } },
      },
    },
  });
}

/* ─────────────────────────────────────────────────────────
   Feature 8 — Sustainability Trend Chart
   Expects dailySeries: array of
     { date, food_redistributed_kg, food_waste_avoided_kg }
   from sustainability_calc.aggregate_by_date()
   ───────────────────────────────────────────────────────── */
function renderSustainabilityTrendChart(canvasId, dailySeries) {
  _destroyExisting(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (!dailySeries || dailySeries.length === 0) {
    canvas.parentElement.innerHTML =
      '<div class="chart-placeholder">No trend data available yet.</div>';
    return;
  }

  const labels      = dailySeries.map(d => d.date);
  const redistributed = dailySeries.map(d => d.food_redistributed_kg ?? 0);
  const avoided     = dailySeries.map(d => d.food_waste_avoided_kg  ?? 0);

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Food Redistributed (kg)',
          data: redistributed,
          borderColor: GREEN,
          backgroundColor: 'rgba(30,132,73,.10)',
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
        },
        {
          label: 'Waste Avoided (kg)',
          data: avoided,
          borderColor: BRAND_L,
          backgroundColor: 'rgba(46,134,193,.08)',
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top' } },
      scales: {
        x: { grid: { color: '#edf1f5' } },
        y: { beginAtZero: true, grid: { color: '#edf1f5' } },
      },
    },
  });
}

/* ─────────────────────────────────────────────────────────
   Feature 10 — Explainability Feature Importance Chart
   Expects rankedFactors: array of
     { feature, importance, effect }
   from explainability.explain_prediction()
   ───────────────────────────────────────────────────────── */
function renderFeatureImportanceChart(canvasId, rankedFactors) {
  _destroyExisting(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (!rankedFactors || rankedFactors.length === 0) {
    canvas.parentElement.innerHTML =
      '<div class="chart-placeholder">No feature importance data available.</div>';
    return;
  }

  // Show top 12 features max
  const top = rankedFactors.slice(0, 12);
  const labels = top.map(f => f.feature);
  const values = top.map(f => f.importance ?? 0);

  // Colour gradient: top feature gets brand blue, rest lighter
  const maxVal = Math.max(...values, 0.0001);
  const colors = values.map(v => {
    const t = v / maxVal;
    const r = Math.round(26  + (46-26)*t);
    const g = Math.round(82  + (134-82)*t);
    const b = Math.round(118 + (193-118)*t);
    return `rgb(${r},${g},${b})`;
  });

  _chartInstances[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Feature Importance',
        data: values,
        backgroundColor: colors,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `Importance: ${(ctx.parsed.x * 100).toFixed(2)}%`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Importance (normalised)' },
          ticks: { callback: v => (v * 100).toFixed(1) + '%' },
          grid: { color: '#edf1f5' },
        },
        y: { grid: { display: false } },
      },
    },
  });
}

/* Expose to global scope for dashboard.js */
window.BSCharts = {
  renderDemandChart,
  renderSurplusRiskChart,
  renderSustainabilityTrendChart,
  renderFeatureImportanceChart,
};
