/* ============================================================
   BhojanSetu — map.js
   Leaflet.js route map rendering.
   Consumes OptimizedRoute.to_dict() response from backend.
   Feature 6 — Software-based Pickup & Route Optimisation.
   ⚠ Backend pending: GET /api/route
   ============================================================ */

'use strict';

let _leafletMap = null;
let _routeLayer = null;

/* ─────────────────────────────────────────────────────────
   initRouteMap
   containerId: id of the map div element
   routeData:   OptimizedRoute.to_dict() response object
                { total_km, algorithm, stops[], warnings[] }
   ───────────────────────────────────────────────────────── */
function initRouteMap(containerId, routeData) {
  // Remove existing map instance if re-initialising
  if (_leafletMap) {
    _leafletMap.remove();
    _leafletMap = null;
    _routeLayer = null;
  }

  const container = document.getElementById(containerId);
  if (!container) return;

  // Remove the placeholder overlay
  const placeholder = document.getElementById('mapPlaceholder');
  if (placeholder) placeholder.style.display = 'none';

  // If no route data, show placeholder and return
  if (!routeData || !routeData.stops || routeData.stops.length === 0) {
    if (placeholder) placeholder.style.display = '';
    return;
  }

  // Find a valid centre (first stop with coordinates)
  const firstWithCoords = routeData.stops.find(s => s.lat != null && s.lon != null);
  const center = firstWithCoords
    ? [firstWithCoords.lat, firstWithCoords.lon]
    : [28.6139, 77.2090]; // fallback: New Delhi

  // Initialise map
  _leafletMap = L.map(containerId, { zoomControl: true }).setView(center, 12);

  // OpenStreetMap tile layer (free, no API key required)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(_leafletMap);

  const coordStops = routeData.stops.filter(s => s.lat != null && s.lon != null);
  const latlngs    = coordStops.map(s => [s.lat, s.lon]);

  // Draw polyline connecting stops in order
  if (latlngs.length > 1) {
    _routeLayer = L.polyline(latlngs, {
      color: '#1a5276',
      weight: 3,
      opacity: 0.8,
      dashArray: null,
    }).addTo(_leafletMap);
    _leafletMap.fitBounds(_routeLayer.getBounds(), { padding: [40, 40] });
  }

  // Place markers
  routeData.stops.forEach((stop, idx) => {
    if (stop.lat == null || stop.lon == null) return;

    const isDepot = stop.is_depot === true;
    const color   = isDepot ? '#1e8449' : '#d35400';
    const radius  = isDepot ? 10 : 8;

    const circleMarker = L.circleMarker([stop.lat, stop.lon], {
      radius,
      fillColor: color,
      color: '#fff',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.9,
    }).addTo(_leafletMap);

    const distText = stop.segment_km_to_next != null
      ? `<br>Next: ${stop.segment_km_to_next.toFixed(2)} km`
      : '';
    const cumText  = stop.cumulative_km != null
      ? `<br>Cumulative: ${stop.cumulative_km.toFixed(2)} km`
      : '';

    circleMarker.bindPopup(
      `<strong>${stop.name}</strong><br>` +
      `Type: ${stop.stop_type}<br>` +
      `Urgency: ${stop.urgency || '—'}<br>` +
      `Stop #${idx}` +
      cumText + distText,
      { maxWidth: 200 }
    );
  });

  // Populate stop list in sidebar
  _renderStopList(routeData);

  // Show distance badge
  const badge = document.getElementById('routeDistanceBadge');
  const kmEl  = document.getElementById('routeTotalKm');
  if (badge) badge.style.display = '';
  if (kmEl)  kmEl.textContent = routeData.total_km != null
    ? routeData.total_km.toFixed(2) : '—';

  // Show route warnings
  _renderRouteWarnings(routeData.warnings || []);
}

/* ── Stop list renderer ──────────────────────────────────── */
function _renderStopList(routeData) {
  const card = document.getElementById('stopListCard');
  const body = document.getElementById('stopListBody');
  if (!card || !body) return;

  card.style.display = '';
  body.innerHTML = '';

  routeData.stops.forEach((stop, idx) => {
    const isDepot = stop.is_depot === true;
    const div = document.createElement('div');
    div.className = 'route-stop-item';
    div.innerHTML =
      `<div class="route-stop-num ${isDepot ? 'depot' : ''}">${idx}</div>` +
      `<div style="flex:1;">` +
        `<div style="font-weight:600; font-size:0.9rem;">${_esc(stop.name)}</div>` +
        `<div style="font-size:0.75rem; color:var(--color-text-muted);">` +
          `${stop.stop_type} — ` +
          (stop.lat != null ? `${stop.lat.toFixed(4)}, ${stop.lon.toFixed(4)}` : 'No coordinates') +
        `</div>` +
      `</div>` +
      `<div style="text-align:right; font-size:0.75rem; color:var(--color-text-muted);">` +
        (stop.cumulative_km != null ? `${stop.cumulative_km.toFixed(2)} km` : '') +
      `</div>`;
    body.appendChild(div);
  });
}

/* ── Route warnings renderer ─────────────────────────────── */
function _renderRouteWarnings(warnings) {
  const warnSection = document.getElementById('routeWarnings');
  const warnList    = document.getElementById('routeWarningList');
  if (!warnSection || !warnList) return;

  if (!warnings || warnings.length === 0) {
    warnSection.style.display = 'none';
    return;
  }
  warnSection.style.display = '';
  warnList.innerHTML = warnings
    .map(w => `<li>${_esc(w)}</li>`)
    .join('');
}

/* ── Utility: HTML escape ────────────────────────────────── */
function _esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/* Expose to global scope */
window.BSMap = { initRouteMap };
