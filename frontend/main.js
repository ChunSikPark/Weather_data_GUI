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
  selectedRegions: null,     // null | { layer: 'states'|'iso'|'custom', ids?: string[], bbox?: number[] }
  regionPanelRendered: false,
  regionCatalog: null,       // { states: [...], iso: [...] }
  regionActiveTab: 'states',
  selectedTimeCrop: { start: null, end: null },  // ISO strings or null
  timeCropPanelRendered: false,
};

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const els = {
  step1: $('step1'),
  step2: $('step2'),
  step3: $('step3'),
  catalogLoading: $('catalog-loading'),
  step1Error: $('step1-error'),
  step1ErrorMsg: $('step1-error-msg'),
  sourceGrid: $('source-grid'),
  typeGrid: $('type-grid'),
  step3Controls: $('step3-controls'),
  downloadBar: $('download-bar'),
  downloadSummaryText: $('download-summary-text'),
  downloadError: $('download-error'),
  downloadProgressBar: $('download-progress-bar'),
  downloadProgressFill: $('download-progress-fill'),
  downloadProgressText: $('download-progress-text'),
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
      key: 'current',
      icon: '📅',
      name: 'Current Year',
      tag: 'Current',
      desc: 'This year\'s monthly HRRR archives, CONUS',
    },
    {
      key: 'archive',
      icon: '🗄️',
      name: 'Archives',
      tag: 'Archive',
      desc: 'Past years\' monthly HRRR archives',
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
      key: 'recent',
      icon: '🔮',
      name: 'Recent',
      tag: '16 Days',
      desc: 'Latest 16 days of GFS forecast cycles',
    },
    {
      key: 'archive',
      icon: '📅',
      name: 'Archive',
      tag: 'Archive',
      desc: 'Archived GFS forecast cycles',
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
    if (selectedType === 'current') return 'hrrr_history_current';
    if (selectedType === 'archive') return 'hrrr_history_archive';
    return 'hrrr_forecast';
  }
  if (selectedSource === 'noaa') {
    return selectedType === 'archive' ? 'noaa_forecast_archive' : 'noaa_forecast_recent';
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
function setCatalogLoading(loading) {
  els.catalogLoading.classList.toggle('hidden', !loading);
  els.sourceGrid.querySelectorAll('.source-card').forEach((c) =>
    c.classList.toggle('loading', loading)
  );
}

async function fetchCatalog() {
  setCatalogLoading(true);
  try {
    state.catalog = await fetchJSON('/api/catalog');
  } catch (err) {
    showStep1Error(`Failed to load catalog: ${err.message}`);
    state.catalog = null;
  } finally {
    setCatalogLoading(false);
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
  state.selectedRegions = null;
  state.regionPanelRendered = false;
  state.selectedTimeCrop = { start: null, end: null };
  state.timeCropPanelRendered = false;

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
  state.selectedRegions = null;
  state.selectedTimeCrop = { start: null, end: null };
  state.timeCropPanelRendered = false;

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
  } else if (selectedSource === 'hrrr' && selectedType === 'current') {
    renderDayPicker('hrrr_history_current');
  } else if (selectedSource === 'hrrr' && selectedType === 'archive') {
    renderMonthPicker('hrrr_history_archive');
  } else if (selectedSource === 'hrrr' && selectedType === 'forecast') {
    renderCyclePicker('hrrr_forecast');
  } else if (selectedSource === 'noaa' && selectedType === 'recent') {
    renderCyclePicker('noaa_forecast_recent');
  } else if (selectedSource === 'noaa' && selectedType === 'archive') {
    renderCyclePicker('noaa_forecast_archive');
  }

  renderRegionPanelOnce();
  renderTimeCropPanelOnce();
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

  // Range selector
  const rangeRow = document.createElement('div');
  rangeRow.className = 'range-selector-row';

  const makeSelect = (id, opts, defaultVal) => {
    const sel = document.createElement('select');
    sel.className = 'range-select';
    sel.id = id;
    opts.forEach((q) => {
      const o = document.createElement('option');
      o.value = q;
      o.textContent = q;
      sel.appendChild(o);
    });
    sel.value = defaultVal;
    return sel;
  };

  const quartersSorted = [...quarters].sort(); // oldest → newest for sensible From/To
  const fromSel = makeSelect('era5-range-from', quartersSorted, quartersSorted[0]);
  const toSel   = makeSelect('era5-range-to',   quartersSorted, quartersSorted[quartersSorted.length - 1]);

  const applyBtn = document.createElement('button');
  applyBtn.className = 'range-apply-btn';
  applyBtn.textContent = 'Select Range';

  rangeRow.appendChild(Object.assign(document.createElement('span'), { className: 'range-label', textContent: 'From' }));
  rangeRow.appendChild(fromSel);
  rangeRow.appendChild(Object.assign(document.createElement('span'), { className: 'range-arrow', textContent: '→' }));
  rangeRow.appendChild(toSel);
  rangeRow.appendChild(applyBtn);
  container.appendChild(rangeRow);

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
      cell.dataset.quarter = key;
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

  // Wire range Apply after grid exists so querySelectorAll finds the cells
  applyBtn.addEventListener('click', () => {
    const [start, end] = [fromSel.value, toSel.value].sort();
    state.selectedDates.clear();
    quarters.forEach((q) => {
      if (q >= start && q <= end && available.has(q)) state.selectedDates.add(q);
    });
    grid.querySelectorAll('.quarter-cell[data-quarter]').forEach((cell) => {
      cell.classList.toggle('selected', state.selectedDates.has(cell.dataset.quarter));
    });
    updateDownloadBar();
  });
}

// ── Month Picker (HRRR Historical) ───────────────────────────────────────────
function renderMonthPicker(catalogKey) {
  const container = els.step3Controls;
  const months = getCatalogList(catalogKey, 'months');
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

// ── Day Picker (HRRR Current Year — individual daily files) ──────────────────
function renderDayPicker(catalogKey) {
  const container = els.step3Controls;
  const days = getCatalogList(catalogKey, 'days');
  const sorted = [...days].sort((a, b) => String(b).localeCompare(String(a)));

  if (sorted.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'no-selection-msg';
    msg.textContent = 'No daily data available in catalog.';
    container.appendChild(msg);
    return;
  }

  const header = document.createElement('div');
  header.className = 'cycle-list-header';
  header.textContent = `${sorted.length} days available — select one or more`;
  container.appendChild(header);

  const list = document.createElement('div');
  list.className = 'cycle-list';
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-multiselectable', 'true');
  list.setAttribute('aria-label', 'Available days');

  sorted.forEach((raw) => {
    const isDay = raw.length === 10; // YYYY-MM-DD
    let label = raw;
    if (isDay) {
      const p = parseMonth(raw.slice(0, 7));
      const day = parseInt(raw.slice(8, 10), 10);
      label = p ? `${MONTHS_SHORT[p.month - 1]} ${day}, ${p.year}` : raw;
    } else {
      const p = parseMonth(raw);
      label = p ? `${MONTHS_SHORT[p.month - 1]} ${p.year}` : raw;
    }
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
    dateEl.textContent = label;

    item.appendChild(checkbox);
    item.appendChild(dateEl);

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
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });

    list.appendChild(item);
  });

  container.appendChild(list);
}

// ── Cycle Picker (HRRR Forecast / NOAA Forecast) ─────────────────────────────
function renderCyclePicker(catalogKey) {
  const container = els.step3Controls;
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
  updateRegionPanel();
  updateTimeCropPanel();
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
    if (selectedType === 'current') sourceLabel = 'HRRR Historical (Current Year)';
    else if (selectedType === 'archive') sourceLabel = 'HRRR Historical (Archive)';
    else sourceLabel = 'HRRR Forecast';
  } else if (selectedSource === 'noaa') {
    sourceLabel = selectedType === 'archive' ? 'NOAA / GFS Archive' : 'NOAA / GFS Recent';
  }

  // Sort and format selected dates
  const sortedDates = [...selectedDates].sort();
  let datesLabel = '';
  if (selectedSource === 'era5') {
    datesLabel = sortedDates.join(', ');
  } else if (selectedSource === 'hrrr' && selectedType === 'current') {
    datesLabel = sortedDates.map((d) => {
      if (d.length === 10) {
        const p = parseMonth(d.slice(0, 7));
        const day = parseInt(d.slice(8, 10), 10);
        return p ? `${MONTHS_SHORT[p.month - 1]} ${day}, ${p.year}` : d;
      }
      const p = parseMonth(d);
      return p ? `${MONTHS_SHORT[p.month - 1]} ${p.year}` : d;
    }).join(', ');
  } else if (selectedSource === 'hrrr' && selectedType === 'archive') {
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
  const regionLabel = _buildRegionLabel();
  const summary = `${sourceLabel} — ${datesLabel}${regionLabel} (${count} ${fileWord}${archiveHint})`;

  els.downloadSummaryText.textContent = summary;
  els.downloadSummaryText.classList.add('has-selection');
  els.btnDownload.disabled = false;
}

// ── Download action ──────────────────────────────────────────────────────────
function buildDownloadURL() {
  const sourceKey = getApiSourceKey();
  const dates = [...state.selectedDates].sort().join(',');
  const sel = state.selectedRegions;
  if (!sel) {
    return `${API_BASE}/api/download?source=${encodeURIComponent(sourceKey)}&dates=${encodeURIComponent(dates)}`;
  }
  let url = `${API_BASE}/api/download/region?source=${encodeURIComponent(sourceKey)}&dates=${encodeURIComponent(dates)}`;
  if (sel.layer === 'custom') {
    url += `&bbox=${sel.bbox.join(',')}`;
  } else {
    url += `&region_layer=${sel.layer}&region_ids=${sel.ids.join(',')}`;
  }
  const tc = state.selectedTimeCrop;
  if (state.selectedDates.size === 1 && tc.start) url += `&time_start=${encodeURIComponent(tc.start)}`;
  if (state.selectedDates.size === 1 && tc.end)   url += `&time_end=${encodeURIComponent(tc.end)}`;
  return url;
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

function _fmtBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function showProgressBar(indeterminate) {
  els.downloadProgressBar.classList.remove('hidden');
  els.downloadProgressFill.style.width = '0%';
  els.downloadProgressFill.classList.toggle('indeterminate', indeterminate);
}

function setProgressBar(pct) {
  els.downloadProgressFill.classList.remove('indeterminate');
  els.downloadProgressFill.style.width = `${Math.min(100, pct * 100).toFixed(1)}%`;
}

function setProgressText(text) {
  els.downloadProgressText.textContent = text;
  els.downloadProgressText.classList.remove('hidden');
}

function hideProgress() {
  els.downloadProgressBar.classList.add('hidden');
  els.downloadProgressFill.style.width = '0%';
  els.downloadProgressFill.classList.remove('indeterminate');
  els.downloadProgressText.classList.add('hidden');
  els.downloadProgressText.textContent = '';
}

function showDownloadError(msg) {
  els.downloadError.textContent = msg;
  els.downloadError.classList.remove('hidden');
}

async function _fetchWithProgress(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(text || `HTTP ${res.status}`);
  }

  const contentLength = parseInt(res.headers.get('Content-Length') || '0', 10);
  const hasLength = contentLength > 0;
  showProgressBar(!hasLength);

  const reader = res.body.getReader();
  const chunks = [];
  let received = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    if (hasLength) {
      setProgressBar(received / contentLength);
      const msg = `${_fmtBytes(received)} / ${_fmtBytes(contentLength)} (${Math.round(received / contentLength * 100)}%)`;
      onProgress ? onProgress(msg) : setProgressText(msg);
    } else {
      const msg = `Downloading… ${_fmtBytes(received)}`;
      onProgress ? onProgress(msg) : setProgressText(msg);
    }
  }

  setProgressBar(1);
  const blob = new Blob(chunks);

  // extract filename from Content-Disposition
  let filename = null;
  const cd = res.headers.get('Content-Disposition');
  if (cd) {
    const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/i);
    if (match) filename = match[1].replace(/['"]/g, '');
  }
  return { blob, filename };
}

function _buildSingleRegionURL(dateKey) {
  const sourceKey = getApiSourceKey();
  const sel = state.selectedRegions;
  let url = `${API_BASE}/api/download/region?source=${encodeURIComponent(sourceKey)}&dates=${encodeURIComponent(dateKey)}`;
  if (sel.layer === 'custom') {
    url += `&bbox=${sel.bbox.join(',')}`;
  } else {
    url += `&region_layer=${sel.layer}&region_ids=${sel.ids.join(',')}`;
  }
  return url;
}

function _triggerBlobDownload(blob, filename) {
  const objectURL = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectURL;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectURL), 10_000);
}

function _buildPrepPhases(count, isRegion) {
  // Phases shown while we wait for the first byte from the server. Times are
  // rough — actual progress depends on file sizes and Drive transfer speed.
  if (count === 1 && !isRegion) {
    return [
      'Connecting to Google Drive and starting transfer…',
      'Downloading from Google Drive — large files can take 1–2 minutes…',
      'Still working — almost ready to transfer to your browser…',
    ];
  }
  if (count === 1 && isRegion) {
    return [
      'Server is downloading the file from Google Drive…',
      'Cropping the file to your selected region…',
      'Almost ready — finalizing the cropped file…',
    ];
  }
  // Multi-file
  const action = isRegion
    ? `cropping each to your region`
    : `packaging them into a ZIP`;
  return [
    `Server is downloading ${count} files from Google Drive and ${action}…`,
    `Still working — large multi-file requests can take several minutes…`,
    `Building the ZIP archive — almost ready to start the transfer…`,
    `Finalizing — preparing the download…`,
  ];
}

async function handleDownload() {
  const count = state.selectedDates.size;
  if (count === 0) return;

  const isRegion = !!state.selectedRegions;
  const sourceKey = getApiSourceKey();

  els.downloadError.classList.add('hidden');
  hideProgress();
  setDownloadLoading(true);

  // Rotate through preparation phases while we wait for the first byte from
  // the server. As soon as data starts flowing, _fetchWithProgress takes over
  // and shows real "X MB / Y MB (Z%)" progress.
  const phases = _buildPrepPhases(count, isRegion);
  let phaseIdx = 0;
  setProgressText(phases[0]);
  showProgressBar(true);

  const phaseTimer = setInterval(() => {
    if (phaseIdx < phases.length - 1) {
      phaseIdx++;
      setProgressText(phases[phaseIdx]);
    }
  }, 20_000);

  try {
    const { blob, filename } = await _fetchWithProgress(
      buildDownloadURL(),
      (msg) => {
        clearInterval(phaseTimer);
        setProgressText(`Downloading — ${msg}`);
      },
    );

    let defaultName;
    if (count === 1) {
      const key = [...state.selectedDates][0];
      defaultName = isRegion ? `${sourceKey}_${key}_region.pww` : `${sourceKey}_${key}.pww`;
    } else {
      const suffix = isRegion ? 'region_bundle' : 'bundle';
      defaultName = `${sourceKey}_${suffix}_${count}_files.zip`;
    }
    _triggerBlobDownload(blob, filename || defaultName);
  } catch (err) {
    showDownloadError(`Download failed: ${err.message}`);
  } finally {
    clearInterval(phaseTimer);
    setDownloadLoading(false);
    setTimeout(hideProgress, 2000);
  }
}

// ── Region filter panel ──────────────────────────────────────────────────────

function _buildRegionLabel() {
  const sel = state.selectedRegions;
  if (!sel) return '';
  if (sel.layer === 'states' && sel.ids && sel.ids.length > 0 && state.regionCatalog) {
    const names = sel.ids.map(id => {
      const s = state.regionCatalog.states.find(st => st.id === id);
      return s ? s.name : id;
    });
    return ` → ${names.join(', ')}`;
  }
  if (sel.layer === 'iso' && sel.ids && sel.ids.length > 0 && state.regionCatalog) {
    const zone = state.regionCatalog.iso.find(z => z.id === sel.ids[0]);
    return ` → ${zone ? zone.name : sel.ids[0]}`;
  }
  if (sel.layer === 'custom' && sel.bbox) {
    const [latMax, lonMin, latMin, lonMax] = sel.bbox;
    return ` → Custom (${latMin}°–${latMax}° N, ${lonMin}°–${lonMax}° W)`;
  }
  return '';
}

async function loadRegionCatalogOnce() {
  if (state.regionCatalog) return;
  try {
    state.regionCatalog = await fetchJSON('/api/regions');
  } catch (err) {
    console.warn('[region] Failed to load region catalog:', err);
    state.regionCatalog = { states: [], iso: [] };
  }
}

function renderRegionPanelOnce() {
  if (state.regionPanelRendered) {
    updateRegionPanel();
    return;
  }
  state.regionPanelRendered = true;

  const details = document.createElement('details');
  details.id = 'region-filter-panel';
  details.className = 'region-filter-panel';

  const summary = document.createElement('summary');
  summary.className = 'region-filter-summary';
  summary.textContent = 'Region Filter (optional)';
  details.appendChild(summary);

  const body = document.createElement('div');
  body.className = 'region-filter-body';

  // Tab bar
  const tabBar = document.createElement('div');
  tabBar.className = 'region-tab-bar';
  ['states', 'iso', 'custom'].forEach((tab) => {
    const btn = document.createElement('button');
    btn.className = 'region-tab-btn' + (tab === 'states' ? ' active' : '');
    btn.dataset.tab = tab;
    btn.textContent = tab === 'states' ? 'US States' : tab === 'iso' ? 'ISO Zones' : 'Custom Bbox';
    btn.addEventListener('click', () => {
      state.regionActiveTab = tab;
      state.selectedRegions = null;
      tabBar.querySelectorAll('.region-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
      renderActiveTabContent(tabContent);
      updateDownloadBar();
    });
    tabBar.appendChild(btn);
  });
  body.appendChild(tabBar);

  const tabContent = document.createElement('div');
  tabContent.id = 'region-tab-content';
  body.appendChild(tabContent);

  details.appendChild(body);
  els.step3Controls.appendChild(details);

  details.addEventListener('toggle', () => {
    if (details.open) loadRegionCatalogOnce().then(() => renderActiveTabContent(tabContent));
  });

  updateRegionPanel();
}

function renderActiveTabContent(container) {
  container.innerHTML = '';
  const tab = state.regionActiveTab;

  if (tab === 'states') {
    renderStatesTab(container);
  } else if (tab === 'iso') {
    renderIsoTab(container);
  } else {
    renderCustomTab(container);
  }
}

function renderStatesTab(container) {
  const cat = state.regionCatalog;
  if (!cat || cat.states.length === 0) {
    container.textContent = 'Loading states…';
    loadRegionCatalogOnce().then(() => { container.innerHTML = ''; renderStatesTab(container); });
    return;
  }
  const grid = document.createElement('div');
  grid.className = 'region-states-grid';

  const noneBtn = document.createElement('button');
  noneBtn.className = 'region-state-btn' + (!state.selectedRegions ? ' active' : '');
  noneBtn.textContent = 'None (full data)';
  noneBtn.addEventListener('click', () => {
    state.selectedRegions = null;
    grid.querySelectorAll('.region-state-btn').forEach(b => b.classList.remove('active'));
    noneBtn.classList.add('active');
    updateDownloadBar();
  });
  grid.appendChild(noneBtn);

  cat.states.forEach(({ id, name }) => {
    const btn = document.createElement('button');
    const isSelected = state.selectedRegions?.layer === 'states' && state.selectedRegions?.ids?.includes(id);
    btn.className = 'region-state-btn' + (isSelected ? ' active' : '');
    btn.textContent = id;
    btn.title = name;
    btn.dataset.id = id;
    btn.addEventListener('click', () => {
      let cur = state.selectedRegions;
      if (cur?.layer !== 'states') cur = { layer: 'states', ids: [] };
      const idx = cur.ids.indexOf(id);
      if (idx >= 0) cur.ids.splice(idx, 1);
      else cur.ids.push(id);
      state.selectedRegions = cur.ids.length > 0 ? cur : null;
      // update active class
      noneBtn.classList.toggle('active', !state.selectedRegions);
      grid.querySelectorAll('.region-state-btn[data-id]').forEach(b => {
        b.classList.toggle('active', !!state.selectedRegions?.ids?.includes(b.dataset.id));
      });
      // 413 guard
      checkRegionSdkHint(container);
      updateDownloadBar();
    });
    grid.appendChild(btn);
  });
  container.appendChild(grid);
  checkRegionSdkHint(container);
}

function renderIsoTab(container) {
  const cat = state.regionCatalog;
  if (!cat) {
    container.textContent = 'Loading…';
    return;
  }
  if (cat.iso.length === 0) {
    container.textContent = 'No ISO zones available (shapefile may not be loaded).';
    return;
  }
  const list = document.createElement('div');
  list.className = 'region-iso-list';

  const noneBtn = document.createElement('button');
  noneBtn.className = 'region-iso-btn' + (!state.selectedRegions ? ' active' : '');
  noneBtn.textContent = 'None (full data)';
  noneBtn.addEventListener('click', () => {
    state.selectedRegions = null;
    list.querySelectorAll('.region-iso-btn').forEach(b => b.classList.remove('active'));
    noneBtn.classList.add('active');
    updateDownloadBar();
  });
  list.appendChild(noneBtn);

  cat.iso.forEach(({ id, name }) => {
    const btn = document.createElement('button');
    const isSelected = state.selectedRegions?.layer === 'iso' && state.selectedRegions?.ids?.[0] === id;
    btn.className = 'region-iso-btn' + (isSelected ? ' active' : '');
    btn.textContent = name;
    btn.addEventListener('click', () => {
      state.selectedRegions = { layer: 'iso', ids: [id] };
      list.querySelectorAll('.region-iso-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      updateDownloadBar();
    });
    list.appendChild(btn);
  });
  container.appendChild(list);
}

function renderCustomTab(container) {
  const form = document.createElement('div');
  form.className = 'region-custom-form';

  const fields = [
    { id: 'bbox-north', label: 'North lat', placeholder: 'e.g. 37.0' },
    { id: 'bbox-south', label: 'South lat', placeholder: 'e.g. 25.8' },
    { id: 'bbox-west',  label: 'West lon',  placeholder: 'e.g. -106.6' },
    { id: 'bbox-east',  label: 'East lon',  placeholder: 'e.g. -93.5' },
  ];

  const inputs = {};
  const errEl = document.createElement('div');
  errEl.className = 'region-custom-error';

  fields.forEach(({ id, label, placeholder }) => {
    const wrap = document.createElement('div');
    wrap.className = 'region-custom-field';
    const lbl = document.createElement('label');
    lbl.textContent = label;
    lbl.htmlFor = id;
    const inp = document.createElement('input');
    inp.type = 'number';
    inp.step = 'any';
    inp.id = id;
    inp.className = 'region-custom-input';
    inp.placeholder = placeholder;
    inputs[id] = inp;
    wrap.appendChild(lbl);
    wrap.appendChild(inp);
    form.appendChild(wrap);
  });

  const applyBtn = document.createElement('button');
  applyBtn.className = 'region-apply-btn';
  applyBtn.textContent = 'Apply';
  applyBtn.addEventListener('click', () => {
    errEl.textContent = '';
    const north = parseFloat(inputs['bbox-north'].value);
    const south = parseFloat(inputs['bbox-south'].value);
    const west  = parseFloat(inputs['bbox-west'].value);
    const east  = parseFloat(inputs['bbox-east'].value);
    if ([north, south, west, east].some(isNaN)) { errEl.textContent = 'All 4 fields required.'; return; }
    if (north <= south) { errEl.textContent = 'North must be greater than South.'; return; }
    if (east <= west) { errEl.textContent = 'East must be greater than West.'; return; }
    if (north > 90 || south < -90) { errEl.textContent = 'Latitude must be between -90 and 90.'; return; }
    if (east > 180 || west < -180) { errEl.textContent = 'Longitude must be between -180 and 180.'; return; }
    state.selectedRegions = { layer: 'custom', bbox: [north, west, south, east] };
    updateDownloadBar();
  });
  form.appendChild(applyBtn);
  form.appendChild(errEl);
  container.appendChild(form);
}

function checkRegionSdkHint(container) {
  const existing = container.querySelector('.region-sdk-hint');
  if (existing) existing.remove();
  const sel = state.selectedRegions;
  if (!sel || sel.layer !== 'states') return;
  const src = state.selectedSource;
  const typ = state.selectedType;
  if (src !== 'hrrr' || typ !== 'archive') return;
  if (sel.ids && state.regionCatalog) {
    try {
      const bboxes = sel.ids.map(id => {
        const s = state.regionCatalog.states.find(st => st.id === id);
        return s ? s.bbox : null;
      }).filter(Boolean);
      if (bboxes.length > 0) {
        const latMax = Math.max(...bboxes.map(b => b[0]));
        const lonMin = Math.min(...bboxes.map(b => b[1]));
        const latMin = Math.min(...bboxes.map(b => b[2]));
        const lonMax = Math.max(...bboxes.map(b => b[3]));
        const area = (latMax - latMin) * (lonMax - lonMin);
        if (area >= 2380) {
          const hint = document.createElement('div');
          hint.className = 'region-sdk-hint';
          hint.textContent = 'CONUS-scale + HRRR archive exceeds server memory. Use the Python SDK: client.hrrr.download_region(months=[...], bbox=(...))';
          container.appendChild(hint);
        }
      }
    } catch {}
  }
}

function updateRegionPanel() {
  const panel = document.getElementById('region-filter-panel');
  if (!panel) return;
  const hasSelection = state.selectedDates.size > 0;
  panel.classList.toggle('hidden', !hasSelection);
  if (!hasSelection) {
    state.selectedRegions = null;
  }
}

// ── Time Crop Panel ───────────────────────────────────────────────────────────
const _TC_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
// rebuildDays functions keyed by 'start'/'end', set during renderTimeCropPanelOnce
const _tcRebuild = {};

function _setTimeCropField(key, dateStr, hourStr) {
  const [y, mo, d] = dateStr.split('-').map(Number);
  const ySel = document.getElementById(`time-crop-${key}-year`);
  const mSel = document.getElementById(`time-crop-${key}-month`);
  const dSel = document.getElementById(`time-crop-${key}-day`);
  const hSel = document.getElementById(`time-crop-${key}-hour`);
  if (ySel) ySel.value = y;
  if (mSel) mSel.value = mo;
  if (_tcRebuild[key]) _tcRebuild[key]();
  if (dSel) dSel.value = d;
  if (hSel) hSel.value = hourStr;
  state.selectedTimeCrop[key] = `${dateStr}T${hourStr}:00:00`;
}

function renderTimeCropPanelOnce() {
  if (state.timeCropPanelRendered) {
    updateTimeCropPanel();
    return;
  }
  state.timeCropPanelRendered = true;

  const details = document.createElement('details');
  details.id = 'time-crop-panel';
  details.className = 'region-filter-panel';

  const summary = document.createElement('summary');
  summary.className = 'region-filter-summary';
  summary.textContent = 'Date & Time Filter (optional)';
  details.appendChild(summary);

  const body = document.createElement('div');
  body.className = 'region-filter-body';

  const note = document.createElement('p');
  note.id = 'time-crop-disabled-note';
  note.className = 'time-crop-disabled-note hidden';
  body.appendChild(note);

  const row = document.createElement('div');
  row.id = 'time-crop-inputs';
  row.className = 'time-crop-inputs';

  const makeField = (labelText, key) => {
    const wrap = document.createElement('div');
    wrap.className = 'time-crop-field';
    const lbl = document.createElement('span');
    lbl.textContent = labelText;
    wrap.appendChild(lbl);

    const inner = document.createElement('div');
    inner.className = 'time-crop-field-inner';

    // Year select
    const ySel = document.createElement('select');
    ySel.id = `time-crop-${key}-year`;
    ySel.className = 'time-crop-input time-crop-year';
    for (let y = 1940; y <= 2035; y++) {
      const o = document.createElement('option');
      o.value = y; o.textContent = y;
      ySel.appendChild(o);
    }

    // Month select
    const mSel = document.createElement('select');
    mSel.id = `time-crop-${key}-month`;
    mSel.className = 'time-crop-input time-crop-month';
    _TC_MONTHS.forEach((name, i) => {
      const o = document.createElement('option');
      o.value = i + 1; o.textContent = name;
      mSel.appendChild(o);
    });

    // Day select — rebuilt whenever year/month change
    const dSel = document.createElement('select');
    dSel.id = `time-crop-${key}-day`;
    dSel.className = 'time-crop-input time-crop-day';

    const rebuildDays = () => {
      const curDay = parseInt(dSel.value) || 1;
      const lastDay = new Date(parseInt(ySel.value), parseInt(mSel.value), 0).getDate();
      dSel.innerHTML = '';
      for (let d = 1; d <= lastDay; d++) {
        const o = document.createElement('option');
        o.value = d; o.textContent = String(d).padStart(2, '0');
        dSel.appendChild(o);
      }
      dSel.value = Math.min(curDay, lastDay);
    };
    _tcRebuild[key] = rebuildDays;
    rebuildDays();

    // Hour select
    const hSel = document.createElement('select');
    hSel.id = `time-crop-${key}-hour`;
    hSel.className = 'time-crop-input time-crop-hour';
    for (let h = 0; h < 24; h++) {
      const o = document.createElement('option');
      o.value = String(h).padStart(2, '0');
      o.textContent = `${String(h).padStart(2, '0')}:00`;
      hSel.appendChild(o);
    }

    const syncState = () => {
      const pad = n => String(n).padStart(2, '0');
      const dateStr = `${ySel.value}-${pad(mSel.value)}-${pad(dSel.value)}`;
      state.selectedTimeCrop[key] = `${dateStr}T${hSel.value}:00:00`;
      updateDownloadBar();
    };

    ySel.addEventListener('change', () => { rebuildDays(); syncState(); });
    mSel.addEventListener('change', () => { rebuildDays(); syncState(); });
    dSel.addEventListener('change', syncState);
    hSel.addEventListener('change', syncState);

    inner.appendChild(ySel);
    inner.appendChild(mSel);
    inner.appendChild(dSel);
    inner.appendChild(hSel);
    wrap.appendChild(inner);
    return wrap;
  };

  row.appendChild(makeField('From', 'start'));
  row.appendChild(makeField('To', 'end'));

  const clearBtn = document.createElement('button');
  clearBtn.className = 'region-state-btn';
  clearBtn.textContent = 'Clear';
  clearBtn.style.marginTop = '6px';
  clearBtn.addEventListener('click', () => {
    state.selectedTimeCrop = { start: null, end: null };
    updateTimeCropPanel();
    updateDownloadBar();
  });
  row.appendChild(clearBtn);

  body.appendChild(row);
  details.appendChild(body);
  els.step3Controls.appendChild(details);

  updateTimeCropPanel();
}

function _quarterDateRange(key) {
  const m = key.match(/^(\d{4})-Q([1-4])$/);
  if (!m) return null;
  const year = parseInt(m[1]);
  const q = parseInt(m[2]);
  const ranges = {
    1: [`${year}-01-01`, `${year}-03-31`],
    2: [`${year}-04-01`, `${year}-06-30`],
    3: [`${year}-07-01`, `${year}-09-30`],
    4: [`${year}-10-01`, `${year}-12-31`],
  };
  const [start, end] = ranges[q];
  return { start, end };
}

function updateTimeCropPanel() {
  const panel = document.getElementById('time-crop-panel');
  if (!panel) return;
  const count = state.selectedDates.size;
  panel.classList.toggle('hidden', count === 0);
  const note = document.getElementById('time-crop-disabled-note');
  const inputs = document.getElementById('time-crop-inputs');
  if (!note || !inputs) return;

  const disable = (msg) => {
    note.textContent = msg;
    note.classList.remove('hidden');
    inputs.classList.add('hidden');
    inputs.querySelectorAll('input, select').forEach(el => { el.disabled = true; });
  };

  if (count !== 1) {
    disable('Select a single date to enable time crop.');
    return;
  }

  // ERA5: apply quarter-based date bounds and latest-quarter guard
  if (state.selectedSource === 'era5') {
    const dateKey = [...state.selectedDates][0];
    const sourceKey = getApiSourceKey();
    const quarters = state.catalog?.[sourceKey]?.quarters || [];
    const latestQ = quarters.length ? [...quarters].sort().at(-1) : null;

    if (dateKey === latestQ) {
      disable('Time crop unavailable — the latest quarter does not contain a full range of data.');
      return;
    }

    const qRange = _quarterDateRange(dateKey);
    if (qRange) {
      const defaults = { start: qRange.start, end: qRange.end };
      const hours = { start: '00', end: '23' };
      ['start', 'end'].forEach(k => {
        const cur = state.selectedTimeCrop[k];
        const curDate = cur ? cur.slice(0, 10) : null;
        if (!curDate || curDate < qRange.start || curDate > qRange.end) {
          _setTimeCropField(k, defaults[k], hours[k]);
        }
      });
    }
  }

  note.classList.add('hidden');
  inputs.classList.remove('hidden');
  inputs.querySelectorAll('input, select').forEach(el => { el.disabled = false; });
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
