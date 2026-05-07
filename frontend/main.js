/**
 * Team Overbye Weather Data Portal — main.js
 * ES module, no build step required.
 */

const API_BASE = window.API_BASE || '';

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  catalog: null,
  selectedSource: null,   // 'era5' | 'hrrr' | 'noaa'
  selectedType: null,     // 'historical' | 'forecast'
  selectedRegion: 'na',   // 'na' | 'tx' (ERA5 only)
  selectedDates: new Set(),
};

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const els = {
  step1: $('step1'),
  step2: $('step2'),
  step3: $('step3'),
  step1Error: $('step1-error'),
  step1ErrorMsg: $('step1-error-msg'),
  sourceGrid: $('source-grid'),
  typeGrid: $('type-grid'),
  step3Controls: $('step3-controls'),
  downloadBar: $('download-bar'),
  downloadSummaryText: $('download-summary-text'),
  downloadError: $('download-error'),
  btnDownload: $('btn-download'),
  btnDownloadLabel: $('btn-download-label'),
  downloadIcon: $('download-icon'),
  dotEra5: $('dot-era5'),
  dotHrrr: $('dot-hrrr'),
  dotNoaa: $('dot-noaa'),
};

// ── Source card definitions ──────────────────────────────────────────────────
const SOURCE_DEFS = {
  era5: {
    icon: '🛰️',
    name: 'ERA5',
    tag: 'Reanalysis',
    desc: 'ERA5 Reanalysis — 0.25° grid, from Copernicus',
  },
  hrrr: {
    icon: '📡',
    name: 'HRRR',
    tag: 'Forecast',
    desc: 'HRRR Forecast — ~3 km resolution, CONUS',
  },
  noaa: {
    icon: '🌐',
    name: 'NOAA / GFS',
    tag: 'Global',
    desc: 'GFS Forecast — 0.25°, North America',
  },
};

// ── Type card definitions per source ────────────────────────────────────────
const TYPE_DEFS = {
  era5: [
    {
      key: 'historical',
      icon: '📅',
      name: 'Historical',
      tag: 'Archive',
      desc: 'Quarterly archives from CDS ERA5',
    },
  ],
  hrrr: [
    {
      key: 'historical',
      icon: '📅',
      name: 'Historical',
      tag: 'Archive',
      desc: 'Monthly archives, CONUS',
    },
    {
      key: 'forecast',
      icon: '🔮',
      name: 'Forecast',
      tag: 'Live',
      desc: '48-hour forecast, updated 4x/day',
    },
  ],
  noaa: [
    {
      key: 'forecast',
      icon: '🔮',
      name: 'Forecast',
      tag: 'Live',
      desc: '384-hour GFS forecast, updated 4x/day',
    },
  ],
};

// ── Source key mapping for API calls ────────────────────────────────────────
function getApiSourceKey() {
  const { selectedSource, selectedType, selectedRegion } = state;
  if (selectedSource === 'era5') {
    return selectedRegion === 'tx' ? 'era5_tx' : 'era5_na';
  }
  if (selectedSource === 'hrrr') {
    return selectedType === 'historical' ? 'hrrr_history' : 'hrrr_forecast';
  }
  if (selectedSource === 'noaa') {
    return 'noaa_forecast';
  }
  return null;
}

// ── Month abbreviations ──────────────────────────────────────────────────────
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// ── Utility: parse "YYYY-Qn" → { year, quarter } ────────────────────────────
function parseQuarter(str) {
  const m = String(str).match(/^(\d{4})-Q(\d)$/i);
  if (!m) return null;
  return { year: parseInt(m[1], 10), quarter: parseInt(m[2], 10) };
}

// ── Utility: parse "YYYY-MM" → { year, month (1-12) } ───────────────────────
function parseMonth(str) {
  const m = String(str).match(/^(\d{4})-(\d{2})$/);
  if (!m) return null;
  return { year: parseInt(m[1], 10), month: parseInt(m[2], 10) };
}

// ── Utility: parse cycle string like "2026-04-21T06Z" ───────────────────────
function parseCycle(str) {
  const m = String(str).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2})Z$/i);
  if (!m) return null;
  return {
    year: parseInt(m[1], 10),
    month: parseInt(m[2], 10),
    day: parseInt(m[3], 10),
    hour: parseInt(m[4], 10),
    raw: str,
  };
}

// ── Utility: format cycle for display ───────────────────────────────────────
function formatCycle(parsed) {
  if (!parsed) return '—';
  const { year, month, day, hour } = parsed;
  const monthName = MONTHS_SHORT[month - 1] || '???';
  const hh = String(hour).padStart(2, '0');
  return {
    date: `${monthName} ${day}, ${year}`,
    utc: `${hh}:00 UTC`,
  };
}

// ── Fetch helpers ────────────────────────────────────────────────────────────
async function fetchJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Status bar ───────────────────────────────────────────────────────────────
function applyStatusDot(el, status) {
  el.className = 'status-dot';
  // status: 'ok' | 'warn' | 'error' | 'idle' | 'loading' | unknown → idle
  const map = {
    ok: 'status-good',
    good: 'status-good',
    running: 'status-good',
    warn: 'status-warn',
    warning: 'status-warn',
    error: 'status-bad',
    bad: 'status-bad',
    idle: 'status-idle',
    loading: 'status-loading',
  };
  el.classList.add(map[String(status).toLowerCase()] || 'status-idle');
}

// API returns hrrr_forecast + hrrr_history separately; show worst for the single HRRR dot.
const _STATUS_PRIORITY = { error: 3, bad: 3, warn: 2, warning: 2, ok: 1, good: 1, running: 1 };
function _worstStatus(a, b) {
  return (_STATUS_PRIORITY[a] || 0) >= (_STATUS_PRIORITY[b] || 0) ? a : b;
}

async function fetchStatus() {
  try {
    // API shape: { noaa, hrrr_forecast, hrrr_history, era5 } — each 'ok'|'error'|'unknown'
    const data = await fetchJSON('/api/status');
    applyStatusDot(els.dotEra5, data.era5 || 'idle');
    applyStatusDot(els.dotHrrr, _worstStatus(data.hrrr_forecast || 'idle', data.hrrr_history || 'idle'));
    applyStatusDot(els.dotNoaa, data.noaa || 'idle');
  } catch {
    applyStatusDot(els.dotEra5, 'idle');
    applyStatusDot(els.dotHrrr, 'idle');
    applyStatusDot(els.dotNoaa, 'idle');
  }
}

// ── Catalog fetch ────────────────────────────────────────────────────────────
async function fetchCatalog() {
  try {
    state.catalog = await fetchJSON('/api/catalog');
  } catch (err) {
    showStep1Error(`Failed to load catalog: ${err.message}`);
    state.catalog = null;
  }
}

function showStep1Error(msg) {
  els.step1ErrorMsg.textContent = msg;
  els.step1Error.classList.remove('hidden');
}

// ── Step 1 — Source selection ────────────────────────────────────────────────
function initSourceCards() {
  const cards = els.sourceGrid.querySelectorAll('.source-card');
  cards.forEach((card) => {
    const source = card.dataset.source;
    card.addEventListener('click', () => selectSource(source));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectSource(source);
      }
    });
  });
}

function selectSource(source) {
  state.selectedSource = source;
  state.selectedType = null;
  state.selectedRegion = 'na';
  state.selectedDates.clear();

  // Update card visual state
  els.sourceGrid.querySelectorAll('.source-card').forEach((c) => {
    const isSelected = c.dataset.source === source;
    c.classList.toggle('selected', isSelected);
    c.setAttribute('aria-pressed', String(isSelected));
  });

  // Render step 2
  renderTypeCards(source);
  showStep(2);
  updateDownloadBar();
}

// ── Step 2 — Type selection ──────────────────────────────────────────────────
function renderTypeCards(source) {
  const types = TYPE_DEFS[source] || [];
  els.typeGrid.innerHTML = '';
  types.forEach((def) => {
    const card = document.createElement('div');
    card.className = 'type-card';
    card.dataset.type = def.key;
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-pressed', 'false');
    card.innerHTML = `
      <div class="card-icon">${def.icon}</div>
      <div class="card-name">${def.name}</div>
      <div class="card-tag">${def.tag}</div>
      <div class="card-desc">${def.desc}</div>
    `;
    card.addEventListener('click', () => selectType(def.key));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectType(def.key);
      }
    });
    els.typeGrid.appendChild(card);
  });
}

function selectType(type) {
  state.selectedType = type;
  state.selectedDates.clear();

  els.typeGrid.querySelectorAll('.type-card').forEach((c) => {
    const isSelected = c.dataset.type === type;
    c.classList.toggle('selected', isSelected);
    c.setAttribute('aria-pressed', String(isSelected));
  });

  renderStep3();
  showStep(3);
  updateDownloadBar();
}

// ── Step visibility ──────────────────────────────────────────────────────────
function showStep(n) {
  [els.step1, els.step2, els.step3].forEach((sec, i) => {
    const stepNum = i + 1;
    if (stepNum <= n) {
      sec.classList.remove('hidden');
      sec.classList.add('active');
    } else {
      sec.classList.add('hidden');
      sec.classList.remove('active');
    }
  });
}

// ── Step 3 — Date picker ─────────────────────────────────────────────────────
function renderStep3() {
  const { selectedSource, selectedType } = state;
  els.step3Controls.innerHTML = '';

  if (selectedSource === 'era5' && selectedType === 'historical') {
    renderQuarterPicker();
  } else if (selectedSource === 'hrrr' && selectedType === 'historical') {
    renderMonthPicker();
  } else if (
    (selectedSource === 'hrrr' && selectedType === 'forecast') ||
    (selectedSource === 'noaa' && selectedType === 'forecast')
  ) {
    renderCyclePicker();
  }
}

// ── Quarter Picker (ERA5 Historical) ─────────────────────────────────────────
function renderQuarterPicker() {
  const container = els.step3Controls;

  // Region toggle
  const toggle = document.createElement('div');
  toggle.className = 'region-toggle';
  toggle.setAttribute('role', 'group');
  toggle.setAttribute('aria-label', 'Select region');

  [
    { key: 'na', label: 'North America' },
    { key: 'tx', label: 'Texas' },
  ].forEach(({ key, label }) => {
    const btn = document.createElement('button');
    btn.className = 'region-btn' + (state.selectedRegion === key ? ' active' : '');
    btn.textContent = label;
    btn.setAttribute('aria-pressed', String(state.selectedRegion === key));
    btn.addEventListener('click', () => {
      state.selectedRegion = key;
      state.selectedDates.clear();
      // re-render
      container.innerHTML = '';
      renderQuarterPicker();
      updateDownloadBar();
    });
    toggle.appendChild(btn);
  });
  container.appendChild(toggle);

  // Get catalog quarters for selected region
  const catalogKey = state.selectedRegion === 'tx' ? 'era5_tx' : 'era5_na';
  const quarters = getCatalogList(catalogKey, 'quarters');

  // Build set of available quarter strings
  const available = new Set(quarters.map(String));

  // Gather unique years, sorted
  const years = [...new Set(
    quarters.map((q) => {
      const p = parseQuarter(q);
      return p ? p.year : null;
    }).filter(Boolean)
  )].sort((a, b) => a - b);

  if (years.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'no-selection-msg';
    msg.textContent = 'No quarterly data available in catalog.';
    container.appendChild(msg);
    return;
  }

  // Build grid
  const grid = document.createElement('div');
  grid.className = 'quarter-grid';

  // Header row
  const header = document.createElement('div');
  header.className = 'quarter-grid-header';
  header.setAttribute('role', 'row');
  ['YEAR', 'Q1', 'Q2', 'Q3', 'Q4'].forEach((label) => {
    const cell = document.createElement('div');
    cell.className = 'qg-header-cell';
    cell.setAttribute('role', 'columnheader');
    cell.textContent = label;
    header.appendChild(cell);
  });
  grid.appendChild(header);

  // Data rows
  years.forEach((year) => {
    const row = document.createElement('div');
    row.className = 'quarter-grid-row';
    row.setAttribute('role', 'row');

    const yearCell = document.createElement('div');
    yearCell.className = 'qg-year-cell';
    yearCell.setAttribute('role', 'rowheader');
    yearCell.textContent = year;
    row.appendChild(yearCell);

    [1, 2, 3, 4].forEach((q) => {
      const key = `${year}-Q${q}`;
      const isAvailable = available.has(key);
      const isSelected = state.selectedDates.has(key);

      const cell = document.createElement('div');
      cell.className = 'quarter-cell';
      cell.setAttribute('role', 'gridcell');
      cell.textContent = `Q${q}`;

      if (isAvailable) {
        cell.classList.add('available');
        if (isSelected) cell.classList.add('selected');
        cell.setAttribute('tabindex', '0');
        cell.setAttribute('aria-label', `${year} Q${q}, ${isSelected ? 'selected' : 'available'}`);
        const toggle = () => {
          if (state.selectedDates.has(key)) {
            state.selectedDates.delete(key);
            cell.classList.remove('selected');
            cell.setAttribute('aria-label', `${year} Q${q}, available`);
          } else {
            state.selectedDates.add(key);
            cell.classList.add('selected');
            cell.setAttribute('aria-label', `${year} Q${q}, selected`);
          }
          updateDownloadBar();
        };
        cell.addEventListener('click', toggle);
        cell.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle();
          }
        });
      } else {
        cell.classList.add('unavailable');
        cell.setAttribute('aria-label', `${year} Q${q}, unavailable`);
        cell.setAttribute('aria-disabled', 'true');
      }

      row.appendChild(cell);
    });

    grid.appendChild(row);
  });

  container.appendChild(grid);
}

// ── Month Picker (HRRR Historical) ───────────────────────────────────────────
function renderMonthPicker() {
  const container = els.step3Controls;
  const months = getCatalogList('hrrr_history', 'months');
  const available = new Set(months.map(String));

  const years = [...new Set(
    months.map((m) => {
      const p = parseMonth(m);
      return p ? p.year : null;
    }).filter(Boolean)
  )].sort((a, b) => a - b);

  if (years.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'no-selection-msg';
    msg.textContent = 'No monthly data available in catalog.';
    container.appendChild(msg);
    return;
  }

  const grid = document.createElement('div');
  grid.className = 'month-grid';

  // Header
  const header = document.createElement('div');
  header.className = 'month-grid-header';
  header.setAttribute('role', 'row');
  const yearHeaderCell = document.createElement('div');
  yearHeaderCell.className = 'mg-header-cell';
  yearHeaderCell.setAttribute('role', 'columnheader');
  yearHeaderCell.textContent = 'YEAR';
  header.appendChild(yearHeaderCell);
  MONTHS_SHORT.forEach((abbr) => {
    const cell = document.createElement('div');
    cell.className = 'mg-header-cell';
    cell.setAttribute('role', 'columnheader');
    cell.textContent = abbr.toUpperCase();
    header.appendChild(cell);
  });
  grid.appendChild(header);

  // Rows
  years.forEach((year) => {
    const row = document.createElement('div');
    row.className = 'month-grid-row';
    row.setAttribute('role', 'row');

    const yearCell = document.createElement('div');
    yearCell.className = 'mg-year-cell';
    yearCell.setAttribute('role', 'rowheader');
    yearCell.textContent = year;
    row.appendChild(yearCell);

    for (let m = 1; m <= 12; m++) {
      const key = `${year}-${String(m).padStart(2, '0')}`;
      const isAvailable = available.has(key);
      const isSelected = state.selectedDates.has(key);
      const monthAbbr = MONTHS_SHORT[m - 1];

      const cell = document.createElement('div');
      cell.className = 'month-cell';
      cell.setAttribute('role', 'gridcell');
      cell.textContent = monthAbbr.slice(0, 1);

      if (isAvailable) {
        cell.classList.add('available');
        if (isSelected) cell.classList.add('selected');
        cell.setAttribute('tabindex', '0');
        cell.setAttribute('aria-label', `${monthAbbr} ${year}, ${isSelected ? 'selected' : 'available'}`);
        const toggle = () => {
          if (state.selectedDates.has(key)) {
            state.selectedDates.delete(key);
            cell.classList.remove('selected');
          } else {
            state.selectedDates.add(key);
            cell.classList.add('selected');
          }
          updateDownloadBar();
        };
        cell.addEventListener('click', toggle);
        cell.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle();
          }
        });
      } else {
        cell.classList.add('unavailable');
        cell.setAttribute('aria-disabled', 'true');
      }

      row.appendChild(cell);
    }

    grid.appendChild(row);
  });

  container.appendChild(grid);
}

// ── Cycle Picker (HRRR Forecast / NOAA Forecast) ─────────────────────────────
function renderCyclePicker() {
  const container = els.step3Controls;
  const catalogKey = state.selectedSource === 'noaa' ? 'noaa_forecast' : 'hrrr_forecast';
  const cycles = getCatalogList(catalogKey, 'cycles');

  // Sort newest first
  const sorted = [...cycles].sort((a, b) => String(b).localeCompare(String(a)));

  if (sorted.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'no-selection-msg';
    msg.textContent = 'No forecast cycles available in catalog.';
    container.appendChild(msg);
    return;
  }

  const header = document.createElement('div');
  header.className = 'cycle-list-header';
  header.textContent = `${sorted.length} cycles available — select one or more`;
  container.appendChild(header);

  const list = document.createElement('div');
  list.className = 'cycle-list';
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-multiselectable', 'true');
  list.setAttribute('aria-label', 'Forecast cycles');

  sorted.forEach((raw) => {
    const parsed = parseCycle(raw);
    const { date, utc } = parsed ? formatCycle(parsed) : { date: raw, utc: '' };
    const isSelected = state.selectedDates.has(raw);

    const item = document.createElement('div');
    item.className = 'cycle-item' + (isSelected ? ' selected' : '');
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', String(isSelected));
    item.setAttribute('tabindex', '0');

    const checkbox = document.createElement('div');
    checkbox.className = 'cycle-checkbox';
    checkbox.setAttribute('aria-hidden', 'true');

    const dateEl = document.createElement('span');
    dateEl.className = 'cycle-date';
    dateEl.textContent = date;

    const utcEl = document.createElement('span');
    utcEl.className = 'cycle-utc';
    utcEl.textContent = utc;

    item.appendChild(checkbox);
    item.appendChild(dateEl);
    item.appendChild(utcEl);

    const toggle = () => {
      if (state.selectedDates.has(raw)) {
        state.selectedDates.delete(raw);
        item.classList.remove('selected');
        item.setAttribute('aria-selected', 'false');
      } else {
        state.selectedDates.add(raw);
        item.classList.add('selected');
        item.setAttribute('aria-selected', 'true');
      }
      updateDownloadBar();
    };

    item.addEventListener('click', toggle);
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle();
      }
    });

    list.appendChild(item);
  });

  container.appendChild(list);
}

// ── Catalog list helper ──────────────────────────────────────────────────────
function getCatalogList(sourceKey, listKey) {
  if (!state.catalog) return [];
  const src = state.catalog[sourceKey];
  if (!src) return [];
  const list = src[listKey];
  if (!Array.isArray(list)) return [];
  return list;
}

// ── Download bar ─────────────────────────────────────────────────────────────
function updateDownloadBar() {
  const { selectedSource, selectedType, selectedRegion, selectedDates } = state;
  const count = selectedDates.size;

  els.downloadError.textContent = '';
  els.downloadError.classList.add('hidden');

  if (!selectedSource || !selectedType || count === 0) {
    els.downloadSummaryText.textContent = 'No data selected';
    els.downloadSummaryText.classList.remove('has-selection');
    els.btnDownload.disabled = true;
    return;
  }

  // Build human-readable label
  let sourceLabel = '';
  if (selectedSource === 'era5') {
    sourceLabel = `ERA5 ${selectedRegion === 'tx' ? 'Texas' : 'North America'}`;
  } else if (selectedSource === 'hrrr') {
    sourceLabel = selectedType === 'historical' ? 'HRRR Historical' : 'HRRR Forecast';
  } else if (selectedSource === 'noaa') {
    sourceLabel = 'NOAA / GFS Forecast';
  }

  // Sort and format selected dates
  const sortedDates = [...selectedDates].sort();
  let datesLabel = '';
  if (selectedSource === 'era5') {
    datesLabel = sortedDates.join(', ');
  } else if (selectedSource === 'hrrr' && selectedType === 'historical') {
    datesLabel = sortedDates.map((d) => {
      const p = parseMonth(d);
      return p ? `${MONTHS_SHORT[p.month - 1]} ${p.year}` : d;
    }).join(', ');
  } else {
    // cycles
    datesLabel = sortedDates.map((d) => {
      const p = parseCycle(d);
      if (!p) return d;
      const { date, utc } = formatCycle(p);
      return `${date} ${utc}`;
    }).join(', ');
  }

  const fileWord = count === 1 ? 'file' : 'files';
  const archiveHint = count > 1 ? ' → ZIP' : '';
  const summary = `${sourceLabel} — ${datesLabel} (${count} ${fileWord}${archiveHint})`;

  els.downloadSummaryText.textContent = summary;
  els.downloadSummaryText.classList.add('has-selection');
  els.btnDownload.disabled = false;
}

// ── Download action ──────────────────────────────────────────────────────────
function buildDownloadURL() {
  const sourceKey = getApiSourceKey();
  const dates = [...state.selectedDates].sort().join(',');
  return `${API_BASE}/api/download?source=${encodeURIComponent(sourceKey)}&dates=${encodeURIComponent(dates)}`;
}

function setDownloadLoading(loading) {
  if (loading) {
    els.btnDownload.classList.add('loading');
    els.downloadIcon.innerHTML = '<span class="spinner-ring"></span>';
    els.btnDownloadLabel.textContent = 'Preparing…';
    els.btnDownload.disabled = true;
  } else {
    els.btnDownload.classList.remove('loading');
    els.downloadIcon.textContent = '⬇';
    els.btnDownloadLabel.textContent = 'Download';
    els.btnDownload.disabled = state.selectedDates.size === 0;
  }
}

function showDownloadError(msg) {
  els.downloadError.textContent = msg;
  els.downloadError.classList.remove('hidden');
}

async function handleDownload() {
  const count = state.selectedDates.size;
  if (count === 0) return;

  const url = buildDownloadURL();

  if (count === 1) {
    // Direct download — navigate to URL
    window.location.href = url;
    return;
  }

  // Multiple files — fetch as blob and trigger download
  setDownloadLoading(true);
  els.downloadError.classList.add('hidden');

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const text = await res.text().catch(() => `HTTP ${res.status}`);
      throw new Error(text || `HTTP ${res.status}`);
    }

    const blob = await res.blob();
    const objectURL = URL.createObjectURL(blob);

    // Infer filename from Content-Disposition or fallback
    let filename = 'weather-data.zip';
    const cd = res.headers.get('Content-Disposition');
    if (cd) {
      const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/i);
      if (match) filename = match[1].replace(/['"]/g, '');
    }

    const a = document.createElement('a');
    a.href = objectURL;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objectURL), 10_000);
  } catch (err) {
    showDownloadError(`Download failed: ${err.message}`);
  } finally {
    setDownloadLoading(false);
  }
}

// ── Initialization ────────────────────────────────────────────────────────────
async function init() {
  // Parallel fetch
  const [, ] = await Promise.allSettled([
    fetchStatus(),
    fetchCatalog(),
  ]);

  // Poll status every 5 minutes
  setInterval(fetchStatus, 5 * 60 * 1000);

  // Wire up source cards (already in HTML)
  initSourceCards();

  // Wire up download button
  els.btnDownload.addEventListener('click', handleDownload);
}

document.addEventListener('DOMContentLoaded', init);
