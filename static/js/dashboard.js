/* ============================================================
   BhojanSetu — dashboard.js
   Central API layer for all dashboard interactions.
   All fetch() calls target live Flask API routes.
   Empty/error states shown when API is unavailable.
   ============================================================ */

'use strict';

/* ── Utility helpers ─────────────────────────────────────── */

const BS = (function () {

  /** HTML-escape a string to prevent XSS */
  function esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /** Show/hide a DOM element */
  function show(id) { const e = document.getElementById(id); if (e) e.style.display = ''; }
  function hide(id) { const e = document.getElementById(id); if (e) e.style.display = 'none'; }
  function text(id, val) { const e = document.getElementById(id); if (e) e.textContent = val; }
  function html(id, val) { const e = document.getElementById(id); if (e) e.innerHTML = val; }

  /** Return a coloured badge HTML for urgency, risk, status, confidence */
  function urgencyBadge(u) {
    return `<span class="badge badge-urgency-${esc(u)}">${esc(u)}</span>`;
  }
  function riskBadge(r) {
    return `<span class="badge badge-risk-${esc(r)}">${esc(r)}</span>`;
  }
  function statusBadge(s) {
    return `<span class="badge badge-status-${esc(s?.toLowerCase())}">${esc(s)}</span>`;
  }
  function confBadge(c) {
    return `<span class="badge badge-conf-${esc(c)}">${esc(c)}</span>`;
  }

  /** Score bar HTML (score = 0-1) */
  function scoreBar(score) {
    const pct = Math.min(100, Math.max(0, (score ?? 0) * 100)).toFixed(1);
    return `<div class="score-bar-wrap">
      <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%"></div></div>
      <span class="score-bar-label">${pct}%</span>
    </div>`;
  }

  /** Show error inside a named element */
  function showErr(id, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.style.display = '';
  }
  function hideErr(id) { hide(id); }

  /* ─── BUG-07 FIX: inline toast instead of alert() ─────────
     Shows a self-dismissing inline notification in a container.
     If containerId is omitted, appends near the top of main-content.
  ────────────────────────────────────────────────────────── */
  function showToast(msg, type = 'info', containerId = null) {
    const typeClass = type === 'success' ? 'alert-success'
                    : type === 'error'   ? 'alert-error'
                    : 'alert-info';
    const div = document.createElement('div');
    div.className = `alert ${typeClass}`;
    div.setAttribute('role', 'alert');
    div.style.cssText = 'margin-bottom:var(--space-4); animation:none;';
    div.innerHTML = `${esc(msg)}
      <button class="alert-close" aria-label="Close" style="margin-left:auto;"
              onclick="this.parentElement.remove()">&times;</button>`;

    let target = containerId ? document.getElementById(containerId) : null;
    if (!target) {
      target = document.querySelector('.main-content');
    }
    if (target) {
      target.prepend(div);
      // Auto-dismiss after 5 seconds
      setTimeout(() => { if (div.parentElement) div.remove(); }, 5000);
    }
  }

  /* ──────────────────────────────────────────────────────────
     Generic fetch wrapper
     Returns { ok, data, error, status }
  ─────────────────────────────────────────────────────────── */
  async function apiFetch(url, options = {}) {
    try {
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        ...options,
      });
      if (response.status === 204) return { ok: true, data: null, status: 204 };
      const data = await response.json();
      if (!response.ok) {
        return {
          ok: false,
          error: data.message || data.error || `HTTP ${response.status}`,
          status: response.status,
        };
      }
      return { ok: true, data, status: response.status };
    } catch (err) {
      return { ok: false, error: 'Network error — could not reach the server.', status: 0 };
    }
  }

  /* ──────────────────────────────────────────────────────────
     Tab switching (surplus exchange page)
  ─────────────────────────────────────────────────────────── */
  function switchTab(btn, panelId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = document.getElementById(panelId);
    if (panel) panel.classList.add('active');
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 1 + 2: DEMAND FORECAST + SURPLUS PREDICTION
     Endpoint: GET /api/demand?center_id=&meal_id=&weeks=&prepared_qty=
     Response: { forecast: [...], surplus_summary: {...}, explanation: {...} }
  ══════════════════════════════════════════════════════════ */
  async function runForecast() {
    const mealSel     = document.getElementById('forecastMeal');
    const weeksSel    = document.getElementById('forecastWeeks');
    const prepQtyEl   = document.getElementById('preparedQty');
    const mealVal     = mealSel?.value;
    const weeksVal    = weeksSel?.value || '7';
    const prepQtyRaw  = prepQtyEl?.value || '';

    hide('forecastEmpty');
    hide('forecastResult');
    hide('forecastError');
    show('forecastLoading');
    hide('explainEmpty');
    hide('explainResult');
    show('explainLoading');

    let url = `/api/demand?weeks=${weeksVal}`;
    if (mealVal) url += `&meal_id=${encodeURIComponent(mealVal)}`;
    if (prepQtyRaw) url += `&prepared_qty=${encodeURIComponent(prepQtyRaw)}`;

    const result = await apiFetch(url);

    hide('forecastLoading');
    hide('explainLoading');

    if (!result.ok) {
      // BUG-02 FIX: distinguish 503 (model loading) from other errors
      let errMsg = result.error;
      if (result.status === 503) {
        errMsg = 'The demand model is still training — this takes about 60–90 seconds on first start. '
               + 'Please wait a moment and try again.';
        // Schedule an automatic retry hint
        const btn = document.getElementById('runForecastBtn');
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Retry in 15s…';
          setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Run Forecast`;
          }, 15000);
        }
      }
      showErr('forecastError', errMsg);
      show('forecastError');
      show('forecastEmpty');
      html('explainResult',
        '<div class="alert alert-info" style="margin:0;">Run a forecast first to see explainability.</div>');
      show('explainResult');
      return;
    }

    const forecastRows = result.data?.forecast || [];
    const surplusSum   = result.data?.surplus_summary || null;

    show('forecastResult');
    if (window.BSCharts) {
      BSCharts.renderDemandChart('demandChart', forecastRows);
    }

    // Feature 2: Surplus risk badge
    if (surplusSum && document.getElementById('surplusRiskBadge')) {
      const rLevel = surplusSum.risk_level || '';
      document.getElementById('surplusRiskBadge').innerHTML =
        `${riskBadge(rLevel)}
         <span style="margin-left:8px; font-size:0.85rem; color:var(--color-text-muted);">
           ${esc(surplusSum.explanation || '')}
         </span>`;
    }

    const confNote = forecastRows[0]?.confidence_note || '';
    text('forecastNote', confNote ? '📊 ' + confNote : '');

    // Feature 10: Explainability
    _renderExplainability(result.data?.explanation);
  }

  /* ─── Feature 10: Explainability renderer ─────────────── */
  function _renderExplainability(explainData) {
    show('explainResult');
    if (!explainData) {
      show('explainUnavailable');
      hide('explainChart');
      return;
    }
    if (explainData.explainable === false) {
      hide('explainChart');
      show('explainUnavailable');
      const el = document.getElementById('explainUnavailable');
      if (el) el.textContent = explainData.message || 'Explainability not available.';
      return;
    }
    hide('explainUnavailable');
    show('explainChart');
    if (window.BSCharts && explainData.ranked_factors) {
      BSCharts.renderFeatureImportanceChart('featureImportanceChart', explainData.ranked_factors);
    }
    const note = explainData.interpretation_note || explainData.description || '';
    text('explainNote', note);
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 2: LOG SURPLUS
     Endpoint: POST /api/surplus
     Request body: { food_item, quantity_kg, date_of_surplus,
                     expiry_time_hours, urgency }
  ══════════════════════════════════════════════════════════ */
  async function submitSurplus(event) {
    if (event) event.preventDefault();

    hide('surplusFormError');
    hide('surplusFormSuccess');

    const form = document.getElementById('surplusForm');
    if (!form) return false;

    const body = {
      food_item:         form.food_item?.value?.trim(),
      quantity_kg:       parseFloat(form.quantity_kg?.value),
      date_of_surplus:   form.date_of_surplus?.value,
      expiry_time_hours: parseFloat(form.expiry_time_hours?.value),
      urgency:           form.urgency?.value,
    };

    if (!body.food_item || isNaN(body.quantity_kg) || body.quantity_kg <= 0 ||
        !body.date_of_surplus || isNaN(body.expiry_time_hours) || !body.urgency) {
      showErr('surplusFormError', 'Please fill all required fields correctly.');
      return false;
    }

    const btn  = document.getElementById('surplusSubmitBtn');
    const spin = document.getElementById('surplusSpinner');
    const txt  = document.getElementById('surplusSubmitText');
    if (btn) btn.disabled = true;
    if (spin) spin.style.display = '';
    if (txt) txt.style.display = 'none';

    const result = await apiFetch('/api/surplus', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    if (btn) btn.disabled = false;
    if (spin) spin.style.display = 'none';
    if (txt) txt.style.display = '';

    if (!result.ok) {
      showErr('surplusFormError', result.error);
      return false;
    }

    const success = document.getElementById('surplusFormSuccess');
    if (success) { success.textContent = 'Surplus logged successfully.'; success.style.display = ''; }
    form.reset();
    const dateField = document.getElementById('surplusDate');
    if (dateField) dateField.valueAsDate = new Date();
    loadSurplusLog();
    return false;
  }

  /* ── Surplus log table loader ────────────────────────── */
  async function loadSurplusLog() {
    hide('surplusLogTable');
    hide('surplusLogEmpty');
    show('surplusLogLoading');

    const result = await apiFetch('/api/surplus');
    hide('surplusLogLoading');

    if (!result.ok) {
      const el = document.getElementById('surplusLogEmpty');
      if (el) {
        const t = el.querySelector('.empty-state-title');
        const d = el.querySelector('.empty-state-desc');
        if (t) t.textContent = 'Could not load surplus log';
        if (d) d.textContent = result.error;
      }
      show('surplusLogEmpty');
      return;
    }

    const rows = result.data?.items || result.data || [];

    // BUG-01 FIX: wire Kitchen KPI — Total Surplus This Month
    const monthKg = result.data?.total_this_month_kg;
    if (monthKg != null) {
      text('kpiSurplus', Number(monthKg).toFixed(1) + ' kg');
    }

    // BUG-01 FIX: wire Pending Matches KPI from surplus log
    const pending = rows.filter(r => r.status === 'confirmed' || r.status === 'pending').length;
    text('kpiMatches', pending);

    if (!rows.length) {
      show('surplusLogEmpty');
      return;
    }

    const tbody = document.getElementById('surplusLogBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td class="col-mono">${esc(r.surplus_id || '—')}</td>
        <td>${esc(r.food_item)}</td>
        <td>${esc(r.quantity_kg)}</td>
        <td>${esc(r.date_of_surplus)}</td>
        <td>${esc(r.expiry_time_hours)} h</td>
        <td>${urgencyBadge(r.urgency)}</td>
        <td>${statusBadge(r.status)}</td>
        <td>
          <a href="/ngo-matches?surplus_id=${esc(r.surplus_id)}"
             class="btn btn-sm btn-ghost">Find NGOs</a>
        </td>
      </tr>`).join('');
    show('surplusLogTable');
  }

  /* ── Surplus dropdown for match/route selects ──────── */
  async function loadSurplusForMatchSelect() {
    const sel = document.getElementById('matchSurplusSelect');
    if (!sel) return;

    const result = await apiFetch('/api/surplus');
    if (!result.ok || !result.data) return;

    const rows = result.data?.items || result.data || [];

    // BUG-22 FIX: pre-select surplus_id from URL query param
    const urlSurplusId = new URLSearchParams(window.location.search).get('surplus_id');

    sel.innerHTML = rows.length
      ? rows.map(r =>
          `<option value="${esc(r.surplus_id)}"
            ${urlSurplusId === r.surplus_id ? 'selected' : ''}>
            ${esc(r.food_item)} — ${esc(r.quantity_kg)} kg (${esc(r.urgency)})
          </option>`
        ).join('')
      : '<option value="">No surplus items available</option>';

    // BUG-22 FIX: if URL had a surplus_id, auto-trigger find
    if (urlSurplusId && rows.some(r => r.surplus_id === urlSurplusId)) {
      findMatches();
    }
  }

  async function loadSurplusForRouteSelect() {
    const sel = document.getElementById('routeSurplusSelect');
    if (!sel) return;

    const result = await apiFetch('/api/surplus');
    if (!result.ok || !result.data) return;

    const rows = result.data?.items || result.data || [];
    sel.innerHTML = rows.length
      ? rows.map(r =>
          `<option value="${esc(r.surplus_id)}">${esc(r.food_item)} — ${esc(r.quantity_kg)} kg</option>`
        ).join('')
      : '<option value="">No surplus items available</option>';
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 4 + 5: NGO MATCHING + NUTRITION (Kitchen side)
     Endpoint: GET /api/matches/find?surplus_id=
     Response: { matches: [NGOMatchResult + nutrition fields] }
  ══════════════════════════════════════════════════════════ */
  async function findMatches() {
    const sel       = document.getElementById('matchSurplusSelect');
    const surplusId = sel?.value;

    hide('matchesEmpty');
    hide('matchesError');
    hide('matchesResultsList');
    show('matchesLoading');

    const result = await apiFetch(
      `/api/matches/find?surplus_id=${encodeURIComponent(surplusId || '')}`
    );
    hide('matchesLoading');

    if (!result.ok) {
      showErr('matchesError', result.error);
      show('matchesError');
      return;
    }

    const matches = result.data?.matches || result.data || [];
    if (!matches.length) {
      show('matchesEmpty');
      return;
    }

    _renderMatchCards(matches);
    show('matchesResultsList');
  }

  /* ─── NGO match cards renderer (Feature 4 + 5) ───────── */
  function _renderMatchCards(matches) {
    const container = document.getElementById('matchesResultsList');
    const template  = document.getElementById('matchCardTemplate');
    if (!container || !template) return;

    container.innerHTML = '';

    matches.forEach((m, idx) => {
      const clone = template.content.cloneNode(true);

      clone.querySelector('.mc-name').textContent     = m.name || m.ngo_id || '—';
      clone.querySelector('.mc-location').textContent = m.location || '—';
      clone.querySelector('.mc-distance').textContent =
        m.distance_km != null ? m.distance_km.toFixed(1) + ' km' : 'Unknown';
      clone.querySelector('.mc-capacity').textContent =
        m.capacity_kg != null ? m.capacity_kg + ' kg' : '—';

      const ub = clone.querySelector('.mc-urgency-badge');
      if (ub) ub.outerHTML = urgencyBadge(m.urgency || 'medium');

      const scoreFill = clone.querySelector('.mc-score-fill');
      const scoreVal  = clone.querySelector('.mc-score-val');
      const pct = Math.min(100, Math.max(0, (m.score ?? 0) * 100));
      if (scoreFill) scoreFill.style.width = pct.toFixed(1) + '%';
      if (scoreVal)  scoreVal.textContent  = pct.toFixed(1) + '%';

      const subScores = clone.querySelector('.mc-sub-scores');
      if (subScores) {
        const items = [
          { label: 'Urgency',  val: m.urgency_score },
          { label: 'Distance', val: m.distance_score },
          { label: 'Capacity', val: m.capacity_score },
          { label: 'Quantity', val: m.quantity_score },
        ];
        subScores.innerHTML = items.map(s => {
          const p = ((s.val ?? 0) * 100).toFixed(0);
          return `<div class="sub-score-item">
            <span class="sub-score-label">${esc(s.label)}</span>
            <div class="sub-score-bar-track">
              <div class="sub-score-bar-fill" style="width:${p}%"></div>
            </div>
            <span style="font-size:10px;">${p}%</span>
          </div>`;
        }).join('');
      }

      // Feature 5: Nutrition
      const nutSection = clone.querySelector('.mc-nutrition-section');
      if (m.nutrition_priority || m.nutrition_profile) {
        if (nutSection) nutSection.style.display = '';
        const np = clone.querySelector('.mc-nutrition-priority');
        const nr = clone.querySelector('.mc-nutrition-reason');
        if (np) np.textContent = m.nutrition_priority || '';
        if (nr) nr.textContent = m.nutrition_reason   || '';

        const profile = m.nutrition_profile;
        const grid = clone.querySelector('.mc-nutrition-grid');
        if (grid && profile && !profile.no_data) {
          const fields = [
            { lbl: 'Calories', val: profile.calories_kcal, unit: 'kcal' },
            { lbl: 'Protein',  val: profile.protein_g,     unit: 'g' },
            { lbl: 'Iron',     val: profile.iron_mg,        unit: 'mg' },
          ];
          grid.innerHTML = fields.map(f => f.val != null ? `
            <div class="nutrition-item">
              <div class="val">${Number(f.val).toFixed(1)}</div>
              <div class="unit">${esc(f.unit)}</div>
              <div class="lbl">${esc(f.lbl)}</div>
            </div>` : '').join('');
        }
      }

      // Reasons collapsible — give unique ID
      const reasonsId = `reasons-${idx}`;
      const toggle = clone.querySelector('.collapse-toggle');
      const content = clone.querySelector('.collapse-content');
      if (toggle) toggle.setAttribute('aria-controls', reasonsId);
      if (content) content.id = reasonsId;

      const reasonsList = clone.querySelector('.mc-reasons-list');
      if (reasonsList && m.reasons) {
        reasonsList.innerHTML = m.reasons.map(r => `<li>${esc(r)}</li>`).join('');
      }

      // Confirm button
      const confirmBtn = clone.querySelector('.mc-confirm-btn');
      if (confirmBtn) {
        // BUG-07 FIX: store data on button, wire to inline feedback
        confirmBtn.dataset.ngoId = m.ngo_id || '';
        confirmBtn.dataset.surplusId = m.surplus_id || '';
        confirmBtn.addEventListener('click', () => {
          confirmMatch(confirmBtn.dataset.ngoId, confirmBtn.dataset.surplusId, confirmBtn);
        });
      }

      container.appendChild(clone);
    });

    // Re-attach collapse toggles on newly injected content
    container.querySelectorAll('.collapse-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = document.getElementById(btn.getAttribute('aria-controls'));
        if (!target) return;
        const open = target.classList.toggle('open');
        btn.setAttribute('aria-expanded', open);
      });
    });
  }

  /* BUG-07 FIX: confirmMatch uses inline feedback, not alert() */
  async function confirmMatch(ngoId, surplusId, triggerBtn) {
    if (triggerBtn) {
      triggerBtn.disabled = true;
      triggerBtn.textContent = 'Confirming…';
    }
    const result = await apiFetch('/api/matches/confirm', {
      method: 'POST',
      body: JSON.stringify({ ngo_id: ngoId, surplus_id: surplusId }),
    });
    if (!result.ok) {
      if (triggerBtn) {
        triggerBtn.disabled = false;
        triggerBtn.textContent = 'Confirm Match';
      }
      showToast('Could not confirm match: ' + result.error, 'error');
    } else {
      if (triggerBtn) {
        triggerBtn.textContent = '✓ Confirmed';
        triggerBtn.className = 'btn btn-secondary btn-sm';
        triggerBtn.disabled = true;
      }
      showToast('Match confirmed successfully.', 'success');
      // Refresh surplus log KPIs
      loadSurplusLog();
    }
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 4+5 (NGO dashboard)
     Endpoint: GET /api/ngo/matches
  ══════════════════════════════════════════════════════════ */
  async function loadNgoMatches() {
    hide('ngoMatchesTable');
    hide('ngoMatchesEmpty');
    hide('ngoMatchesError');
    show('ngoMatchesLoading');

    const result = await apiFetch('/api/ngo/matches');
    hide('ngoMatchesLoading');

    if (!result.ok) {
      showErr('ngoMatchesError', result.error);
      show('ngoMatchesError');
      return;
    }

    const matches = result.data?.matches || result.data || [];

    // BUG-01 FIX: wire NGO dashboard KPIs from match data
    const accepted = matches.filter(m => m.status === 'accepted' || m.status === 'confirmed').length;
    const pending  = matches.filter(m => m.status === 'pending').length;
    const totalKg  = matches
      .filter(m => m.status === 'accepted' || m.status === 'confirmed')
      .reduce((s, m) => s + (parseFloat(m.quantity_kg) || 0), 0);
    const estMeals = Math.round(totalKg / 0.5);

    text('kpiAccepted',      accepted);
    text('kpiFoodReceived',  totalKg.toFixed(1) + ' kg');
    text('kpiMealsServed',   estMeals);
    text('kpiPendingPickups', pending);

    if (!matches.length) { show('ngoMatchesEmpty'); return; }

    const tbody = document.getElementById('ngoMatchesBody');
    if (!tbody) return;

    // BUG-15 FIX: we need kitchen names — fetch kitchen list once then render
    const kitchenResult = await apiFetch('/api/kitchens');
    const kitchenMap = {};
    if (kitchenResult.ok && kitchenResult.data?.kitchens) {
      kitchenResult.data.kitchens.forEach(k => { kitchenMap[k.kitchen_id] = k.name; });
    }

    tbody.innerHTML = matches.map(m => `
      <tr>
        <td>${esc(m.food_item || m.item || '—')}</td>
        <td>${esc(kitchenMap[m.kitchen_id] || m.kitchen_id || '—')}</td>
        <td>${esc(m.quantity_kg)}</td>
        <td>${m.distance_km != null ? Number(m.distance_km).toFixed(1) : '—'}</td>
        <td>${scoreBar(m.score)}</td>
        <td>${urgencyBadge(m.urgency || 'medium')}</td>
        <td>${m.nutrition_priority
              ? `<span class="badge badge-conf-HIGH">${esc(m.nutrition_priority)}</span>`
              : '—'}</td>
        <td>${statusBadge(m.status || 'pending')}</td>
        <td style="display:flex; gap:4px; flex-wrap:wrap;">
          <button class="btn btn-success btn-sm"
            data-mid="${esc(m.match_id)}" data-action="accepted"
            onclick="BS.patchMatchStatus(this.dataset.mid,'accepted',this)">Accept</button>
          <button class="btn btn-danger btn-sm"
            data-mid="${esc(m.match_id)}" data-action="rejected"
            onclick="BS.patchMatchStatus(this.dataset.mid,'rejected',this)">Reject</button>
        </td>
      </tr>`).join('');

    show('ngoMatchesTable');
  }

  /* BUG-07 FIX: patchMatchStatus uses inline toast instead of alert() */
  async function patchMatchStatus(matchId, status, triggerBtn) {
    if (triggerBtn) triggerBtn.disabled = true;
    const result = await apiFetch(`/api/matches/${encodeURIComponent(matchId)}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    if (!result.ok) {
      if (triggerBtn) triggerBtn.disabled = false;
      showToast('Error updating match: ' + result.error, 'error');
    } else {
      showToast(`Match ${status} successfully.`, 'success');
      loadNgoMatches();
    }
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 6: ROUTE OPTIMISATION
     Endpoint: GET /api/route?surplus_id=
  ══════════════════════════════════════════════════════════ */
  async function optimiseRoute() {
    const sel       = document.getElementById('routeSurplusSelect');
    const surplusId = sel?.value;

    hide('routeError');
    show('mapLoading');

    const result = await apiFetch(
      `/api/route?surplus_id=${encodeURIComponent(surplusId || '')}`
    );
    hide('mapLoading');

    if (!result.ok) {
      showErr('routeError', result.error);
      show('routeError');
      return;
    }

    if (window.BSMap) {
      BSMap.initRouteMap('map', result.data);
    }
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 7: PRODUCTION PLANNING
     Endpoint: GET /api/production_planning
  ══════════════════════════════════════════════════════════ */
  async function loadProductionPlanning() {
    hide('planningEmpty');
    hide('planningError');
    hide('recommendationsList');
    show('planningLoading');

    const result = await apiFetch('/api/production_planning');
    hide('planningLoading');

    if (!result.ok) {
      showErr('planningError', result.error);
      show('planningError');
      return;
    }

    const data = result.data;
    const recs = data?.recommendations || [];
    const meta = data?.metadata || {};

    text('planningRecords',    data?.records_analysed ?? '—');
    text('planningTotalItems', meta.total_items_in_surplus ?? '—');
    text('planningRecs',       recs.length);

    if (!recs.length) {
      show('planningEmpty');
      return;
    }

    _renderRecommendationCards(recs);
    show('recommendationsList');
  }

  function _renderRecommendationCards(recs) {
    const container = document.getElementById('recommendationsList');
    const template  = document.getElementById('recCardTemplate');
    if (!container || !template) return;
    container.innerHTML = '';

    recs.forEach((r, idx) => {
      const clone = template.content.cloneNode(true);

      clone.querySelector('.rc-item').textContent           = r.item || '—';
      clone.querySelector('.rc-recommendation').textContent = r.recommendation || '';
      clone.querySelector('.rc-reason').textContent         = r.reason || '';

      const cb = clone.querySelector('.rc-conf-badge');
      if (cb) { cb.textContent = r.confidence || '—'; cb.className = `badge badge-conf-${r.confidence || 'WEAK'}`; }

      const ev = r.evidence || {};
      clone.querySelector('.rc-occurrences').textContent   = ev.surplus_occurrences ?? '—';
      clone.querySelector('.rc-total-records').textContent = ev.total_surplus_records_analysed ?? '—';
      clone.querySelector('.rc-fraction').textContent =
        ev.fraction_of_records != null
          ? (ev.fraction_of_records * 100).toFixed(1) + '%' : '—';
      clone.querySelector('.rc-date-range').textContent    = ev.date_range || '—';

      const procRow = clone.querySelector('.rc-procured-row');
      if (procRow && ev.total_procured_kg != null) {
        procRow.style.display = '';
        clone.querySelector('.rc-procured').textContent = ev.total_procured_kg + ' kg';
      }

      const evidenceId = `evidence-${idx}`;
      const toggle  = clone.querySelector('.collapse-toggle');
      const content = clone.querySelector('.collapse-content');
      if (toggle)  toggle.setAttribute('aria-controls', evidenceId);
      if (content) content.id = evidenceId;

      container.appendChild(clone);
    });

    // Re-wire collapse toggles
    container.querySelectorAll('.collapse-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const t = document.getElementById(btn.getAttribute('aria-controls'));
        if (!t) return;
        btn.setAttribute('aria-expanded', t.classList.toggle('open'));
      });
    });
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 8 + 9: SUSTAINABILITY + ESG REPORT
     Endpoints:
       GET  /api/sustainability
       GET  /api/sustainability/trend
       GET  /api/sustainability/by-kitchen
       POST /api/report/download
  ══════════════════════════════════════════════════════════ */
  async function loadSustainability() {
    hide('trendCard');
    hide('byKitchenCard');
    hide('sustainEmpty');
    hide('sustainError');
    show('sustainLoading');

    const [metResult, trendResult, kitchenResult] = await Promise.all([
      apiFetch('/api/sustainability'),
      apiFetch('/api/sustainability/trend'),
      apiFetch('/api/sustainability/by-kitchen'),
    ]);

    hide('sustainLoading');

    if (!metResult.ok) {
      showErr('sustainError', metResult.error);
      show('sustainError');
      return;
    }

    const d = metResult.data || {};
    if (d.status === 'no_data') { show('sustainEmpty'); return; }

    // KPI cards
    text('metricRedistributed', d.total_food_redistributed_kg != null
      ? Number(d.total_food_redistributed_kg).toFixed(1) : '—');
    text('metricWasteAvoided', d.total_food_waste_avoided_kg != null
      ? Number(d.total_food_waste_avoided_kg).toFixed(1) : '—');
    text('metricMeals', d.total_meals_redistributed ?? '—');
    text('metricMealsSrc',
      d.meals_source === 'estimated_from_kg' ? 'estimated from kg' : 'from records');
    text('metricCo2', d.estimated_co2e_avoided_kg != null
      ? Number(d.estimated_co2e_avoided_kg).toFixed(1) : '—');
    text('metricWater', d.estimated_water_saved_liters != null
      ? Number(d.estimated_water_saved_liters).toFixed(0) : '—');

    // BUG-01 FIX: wire Kitchen CO2 + Meals KPI from sustainability data
    text('kpiCo2',   d.estimated_co2e_avoided_kg != null
      ? Number(d.estimated_co2e_avoided_kg).toFixed(1) : '—');
    text('kpiMeals', d.total_meals_redistributed ?? '—');

    // Trend chart
    if (trendResult.ok && trendResult.data) {
      const daily = trendResult.data.daily_series || [];
      if (daily.length) {
        show('trendCard');
        if (window.BSCharts) {
          BSCharts.renderSustainabilityTrendChart('sustainTrendChart', daily);
        }
        const trend = trendResult.data.trend || 'stable';
        const trendColors = { improving: '#1e8449', declining: '#c0392b', stable: '#d68910' };
        const trendArrows = { improving: '↑', declining: '↓', stable: '→' };
        const badge = document.getElementById('trendBadge');
        if (badge) badge.innerHTML =
          `<span class="badge" style="background:${trendColors[trend] || '#dce3ea'};color:#fff;">
             ${trendArrows[trend] || ''} ${trend.charAt(0).toUpperCase() + trend.slice(1)}
           </span>`;
      }
    }

    // By-kitchen breakdown
    if (kitchenResult.ok && kitchenResult.data) {
      const rows = kitchenResult.data || [];
      if (rows.length) {
        show('byKitchenCard');
        const tbody = document.getElementById('byKitchenBody');
        if (tbody) {
          tbody.innerHTML = rows.map(r => `
            <tr>
              <td class="col-mono">${esc(r.kitchen_id)}</td>
              <td>${Number(r.food_redistributed_kg || 0).toFixed(1)}</td>
              <td>${Number(r.food_waste_avoided_kg || 0).toFixed(1)}</td>
              <td>${r.meals_count ?? '—'}</td>
              <td>${Number(r.estimated_co2e_avoided_kg || 0).toFixed(1)}</td>
              <td>${Number(r.estimated_water_saved_liters || 0).toFixed(0)}</td>
            </tr>`).join('');
        }
      }
    }
  }

  async function downloadReport() {
    hide('reportError');
    hide('reportSuccess');

    const institution = document.getElementById('reportInstitution')?.value?.trim();
    const start       = document.getElementById('reportStart')?.value;
    const end         = document.getElementById('reportEnd')?.value;

    const btn  = document.getElementById('downloadReportBtn');
    const spin = document.getElementById('reportSpinner');
    const txt  = document.getElementById('reportBtnText');
    if (btn)  btn.disabled = true;
    if (spin) spin.style.display = '';
    if (txt)  txt.style.display = 'none';

    const result = await apiFetch('/api/report/download', {
      method: 'POST',
      body: JSON.stringify({
        institution_name: institution,
        reporting_period_start: start,
        reporting_period_end: end,
      }),
    });

    if (btn)  btn.disabled = false;
    if (spin) spin.style.display = 'none';
    if (txt)  txt.style.display = '';

    if (!result.ok) {
      showErr('reportError', result.error);
      show('reportError');
      return;
    }

    if (result.data?.download_url) {
      window.location.href = result.data.download_url;
    } else {
      const success = document.getElementById('reportSuccess');
      if (success) { success.textContent = 'Report generated successfully.'; success.style.display = ''; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     FEATURE 3: RAW MATERIAL EXCHANGE
     Endpoints:
       POST /api/exchange/listing
       GET  /api/exchange/listings
       GET  /api/exchange/matches
       POST /api/exchange/propose
       GET  /api/exchange/mine
  ══════════════════════════════════════════════════════════ */
  async function submitListing(event) {
    if (event) event.preventDefault();

    hide('listingFormError');
    hide('listingFormSuccess');

    const form = document.getElementById('listingForm');
    if (!form) return false;

    const body = {
      ingredient:  form.ingredient?.value?.trim(),
      quantity:    parseFloat(form.quantity?.value),
      unit:        form.unit?.value,
      date_listed: form.date_listed?.value,
      use_by_date: form.use_by_date?.value || null,
    };

    if (!body.ingredient || isNaN(body.quantity) || !body.unit || !body.date_listed) {
      showErr('listingFormError', 'Please fill all required fields.');
      return false;
    }

    const btn  = document.getElementById('listingSubmitBtn');
    const spin = document.getElementById('listingSpinner');
    const txt  = document.getElementById('listingSubmitText');
    if (btn) btn.disabled = true;
    if (spin) spin.style.display = '';
    if (txt) txt.style.display = 'none';

    const result = await apiFetch('/api/exchange/listing', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    if (btn) btn.disabled = false;
    if (spin) spin.style.display = 'none';
    if (txt) txt.style.display = '';

    if (!result.ok) {
      showErr('listingFormError', result.error);
      return false;
    }

    const success = document.getElementById('listingFormSuccess');
    if (success) { success.textContent = 'Material listed successfully.'; success.style.display = ''; }
    form.reset();
    const dateField = document.getElementById('listDate');
    if (dateField) dateField.valueAsDate = new Date();
    loadMyListings();
    return false;
  }

  async function loadMyListings() {
    hide('myListingsTable');
    hide('myListingsEmpty');
    hide('myListingsError');
    show('myListingsLoading');

    const result = await apiFetch('/api/exchange/listings');
    hide('myListingsLoading');

    if (!result.ok) {
      showErr('myListingsError', result.error);
      show('myListingsError');
      return;
    }

    const rows = result.data?.listings || result.data || [];
    if (!rows.length) { show('myListingsEmpty'); return; }

    const tbody = document.getElementById('myListingsBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.ingredient)}</td>
        <td>${esc(r.quantity)}</td>
        <td>${esc(r.unit)}</td>
        <td>${esc(r.date_listed)}</td>
        <td>${esc(r.use_by_date || '—')}</td>
        <td>${statusBadge(r.status || 'AVAILABLE')}</td>
      </tr>`).join('');
    show('myListingsTable');
  }

  async function findExchangeMatches() {
    const ingredient = document.getElementById('needIngredient')?.value?.trim();
    const qty        = document.getElementById('needQty')?.value;
    const date       = document.getElementById('needDate')?.value;
    const urgency    = document.getElementById('needUrgency')?.value || 'medium';

    hide('exchangeMatchEmpty');
    hide('exchangeMatchError');
    hide('exchangeMatchResults');
    show('exchangeMatchLoading');

    const result = await apiFetch(
      `/api/exchange/matches?ingredient=${encodeURIComponent(ingredient || '')}` +
      `&quantity=${encodeURIComponent(qty || '')}&date=${encodeURIComponent(date || '')}` +
      `&urgency=${encodeURIComponent(urgency)}`
    );
    hide('exchangeMatchLoading');

    if (!result.ok) {
      showErr('exchangeMatchError', result.error);
      show('exchangeMatchError');
      return;
    }

    const matches = result.data?.matches || result.data || [];
    if (!matches.length) { show('exchangeMatchEmpty'); return; }

    const container = document.getElementById('exchangeMatchResults');
    if (!container) return;

    container.innerHTML = matches.map((m, i) => `
      <div class="card" style="margin-bottom:var(--space-3);">
        <div class="card-body">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:var(--space-3);">
            <div>
              <strong>${esc(m.listing?.ingredient || '—')}</strong>
              &nbsp; ${esc(m.listing?.quantity)} ${esc(m.listing?.unit)}
              &nbsp; ${statusBadge(m.listing?.status)}
            </div>
            <div>${scoreBar(m.score)}</div>
          </div>
          <div style="font-size:0.8rem; color:var(--color-text-muted); margin-top:4px;">
            Kitchen: ${esc(m.listing?.kitchen_id || '—')} &nbsp;|&nbsp;
            Use by: ${esc(m.listing?.use_by_date || '—')} &nbsp;|&nbsp;
            Distance: ${m.distance_km != null ? m.distance_km.toFixed(1) + ' km' : '—'}
          </div>
          <ul class="reasons-list" style="margin-top:6px;">
            ${(m.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}
          </ul>
          <div id="propose-feedback-${i}" style="display:none; margin-top:6px;"></div>
          <button class="btn btn-sm btn-primary" style="margin-top:8px;"
            data-lid="${esc(m.listing?.listing_id || '')}" data-idx="${i}"
            onclick="BS.proposeExchange(this.dataset.lid, this.dataset.idx)">
            Propose Exchange
          </button>
        </div>
      </div>`).join('');

    show('exchangeMatchResults');
  }

  /* BUG-07 FIX: proposeExchange uses inline feedback, not alert() */
  async function proposeExchange(listingId, cardIdx) {
    const feedbackEl = document.getElementById(`propose-feedback-${cardIdx}`);
    const result = await apiFetch('/api/exchange/propose', {
      method: 'POST',
      body: JSON.stringify({ listing_id: listingId }),
    });
    if (!result.ok) {
      if (feedbackEl) {
        feedbackEl.className = 'alert alert-error';
        feedbackEl.textContent = 'Could not propose exchange: ' + result.error;
        feedbackEl.style.display = '';
      } else {
        showToast('Could not propose exchange: ' + result.error, 'error');
      }
    } else {
      if (feedbackEl) {
        feedbackEl.className = 'alert alert-success';
        feedbackEl.textContent = 'Exchange proposed successfully.';
        feedbackEl.style.display = '';
      } else {
        showToast('Exchange proposed successfully.', 'success');
      }
      loadMyExchanges();
    }
  }

  async function loadMyExchanges() {
    hide('myExchangesTable');
    hide('myExchangesEmpty');
    hide('myExchangesError');
    show('myExchangesLoading');

    const result = await apiFetch('/api/exchange/mine');
    hide('myExchangesLoading');

    if (!result.ok) {
      showErr('myExchangesError', result.error);
      show('myExchangesError');
      return;
    }

    const rows = result.data?.exchanges || result.data || [];
    if (!rows.length) { show('myExchangesEmpty'); return; }

    const tbody = document.getElementById('myExchangesBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.ingredient)}</td>
        <td class="col-mono">${esc(r.offering_kitchen_id)}</td>
        <td class="col-mono">${esc(r.requesting_kitchen_id)}</td>
        <td>${esc(r.offered_quantity)}</td>
        <td>${esc(r.requested_quantity)}</td>
        <td>${esc(r.unit)}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${esc((r.created_at || '').split('T')[0])}</td>
      </tr>`).join('');
    show('myExchangesTable');
  }

  /* ══════════════════════════════════════════════════════════
     ADMIN dashboard loaders
  ══════════════════════════════════════════════════════════ */
  async function loadAdminKitchens() {
    hide('kitchensTable'); hide('kitchensEmpty'); hide('kitchensError');
    show('kitchensLoading');

    const result = await apiFetch('/api/kitchens');
    hide('kitchensLoading');

    if (!result.ok) { showErr('kitchensError', result.error); show('kitchensError'); return; }

    const rows = result.data?.kitchens || result.data || [];
    if (!rows.length) { show('kitchensEmpty'); return; }

    const tbody = document.getElementById('kitchensBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r =>
      `<tr><td class="col-mono">${esc(r.kitchen_id)}</td>
            <td>${esc(r.name)}</td>
            <td>${esc(r.location)}</td></tr>`
    ).join('');
    show('kitchensTable');

    text('kpiKitchens', rows.length);
  }

  async function loadAdminNgos() {
    hide('ngosTable'); hide('ngosEmpty'); hide('ngosError');
    show('ngosLoading');

    const result = await apiFetch('/api/ngos');
    hide('ngosLoading');

    if (!result.ok) { showErr('ngosError', result.error); show('ngosError'); return; }

    const rows = result.data?.ngos || result.data || [];
    if (!rows.length) { show('ngosEmpty'); return; }

    const tbody = document.getElementById('ngosBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r =>
      `<tr><td class="col-mono">${esc(r.ngo_id)}</td>
            <td>${esc(r.name)}</td>
            <td>${esc(r.capacity_kg)}</td>
            <td>${statusBadge(r.status)}</td></tr>`
    ).join('');
    show('ngosTable');

    text('kpiNgos', rows.filter(r => r.status === 'active').length);
  }

  async function loadAdminMatches() {
    hide('allMatchesTable'); hide('allMatchesEmpty'); hide('allMatchesError');
    show('allMatchesLoading');

    const result = await apiFetch('/api/matches');
    hide('allMatchesLoading');

    if (!result.ok) { showErr('allMatchesError', result.error); show('allMatchesError'); return; }

    const rows = result.data?.matches || result.data || [];
    if (!rows.length) { show('allMatchesEmpty'); return; }

    const tbody = document.getElementById('allMatchesBody');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r =>
      `<tr>
        <td class="col-mono">${esc(r.match_id)}</td>
        <td>${esc(r.kitchen_id)}</td>
        <td>${esc(r.ngo_id)}</td>
        <td>${esc(r.food_item)}</td>
        <td>${esc(r.quantity_kg)}</td>
        <td>${scoreBar(r.score)}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${esc((r.created_at || '').split('T')[0])}</td>
      </tr>`).join('');
    show('allMatchesTable');

    text('kpiTotalMatches', rows.length);
  }

  async function loadAdminSustainability() {
    hide('adminSustainData'); hide('adminSustainError');
    show('adminSustainLoading');

    // BUG-01 FIX: also load surplus for kpiTotalSurplus
    const [sustainResult, surplusResult] = await Promise.all([
      apiFetch('/api/sustainability'),
      apiFetch('/api/surplus'),
    ]);

    hide('adminSustainLoading');

    if (!sustainResult.ok) {
      showErr('adminSustainError', sustainResult.error);
      show('adminSustainError');
    } else {
      const d = sustainResult.data || {};
      text('adminRedistributed', Number(d.total_food_redistributed_kg || 0).toFixed(1));
      text('adminCo2', Number(d.estimated_co2e_avoided_kg || 0).toFixed(1));
      text('adminMeals', d.total_meals_redistributed ?? '—');
      show('adminSustainData');
    }

    // BUG-01 FIX: wire "Surplus Logged" KPI
    if (surplusResult.ok && surplusResult.data) {
      const allRows = surplusResult.data?.items || surplusResult.data || [];
      const totalKg = allRows.reduce((s, r) => s + (parseFloat(r.quantity_kg) || 0), 0);
      text('kpiTotalSurplus', totalKg.toFixed(1) + ' kg');
    }
  }

  /* ── BUG-13 FIX: loadMealsDropdown with auto-retry ────── */
  let _mealsRetryTimer = null;

  async function loadMealsDropdown() {
    const sel = document.getElementById('forecastMeal');
    if (!sel) return;

    const result = await apiFetch('/api/meals');
    if (!result.ok || !result.data) return;

    const meals = result.data.meals || [];
    if (!meals.length) {
      sel.innerHTML = '<option value="">Model loading — retrying in 15s…</option>';
      // BUG-13 FIX: schedule automatic retry
      clearTimeout(_mealsRetryTimer);
      _mealsRetryTimer = setTimeout(loadMealsDropdown, 15000);
      return;
    }

    clearTimeout(_mealsRetryTimer);
    sel.innerHTML = meals.map(m =>
      `<option value="${esc(String(m))}">Meal ${esc(String(m))}</option>`
    ).join('');
  }

  /* ── Expose public API ────────────────────────────────── */
  return {
    // Feature 1+2
    runForecast,
    loadSurplusLog,
    submitSurplus,
    loadMealsDropdown,
    loadSurplusForMatchSelect,
    loadSurplusForRouteSelect,
    // Feature 3
    submitListing,
    loadMyListings,
    findExchangeMatches,
    proposeExchange,
    loadMyExchanges,
    // Feature 4+5
    findMatches,
    confirmMatch,
    loadNgoMatches,
    patchMatchStatus,
    // Feature 6
    optimiseRoute,
    // Feature 7
    loadProductionPlanning,
    // Feature 8+9
    loadSustainability,
    downloadReport,
    // Admin
    loadAdminKitchens,
    loadAdminNgos,
    loadAdminMatches,
    loadAdminSustainability,
    // UI
    switchTab,
    // Toast (accessible for inline use)
    showToast,
  };
})();

window.BS = BS;