// Oversikt (compare) page — charts, heatmap, modal, highlights, weekday grid.
// Loaded only on /oversikt via {% block extra_js %} after Chart.js CDN script.

import { apiFetch } from './utils.js';

const turnusLabels = JSON.parse(document.getElementById('compare-labels').textContent);
const metricsData  = JSON.parse(document.getElementById('compare-data').textContent);
const scheduleData = JSON.parse(document.getElementById('compare-schedule').textContent);
const innSchedules = JSON.parse(document.getElementById('compare-inn-schedules').textContent);

let favorites = new Set(JSON.parse(document.getElementById('compare-favoritt').textContent));
let currentModalTurnus = null;
let currentSort = 'desc';
const charts = {};

// ── Constants ────────────────────────────────────────────────────────────────

const SECTIONS = [
    {
        color: '#8b5cf6',
        metrics: [
            { key: 'shift_cnt',            label: 'Dagsverk' },
            { key: 'avg_shift_hours',      label: 'Snitt timer' },
            { key: 'longest_work_streak',  label: 'Lengste rekke' },
            { key: 'longest_off_streak',   label: 'Lengste fri' },
            { key: 'afternoons_in_row',    label: 'Ettermiddag på rad' },
        ],
    },
];

const HEATMAP_COLS = [
    { key: 'natt',         group: 'vakttyper' },
    { key: 'tidlig',       group: 'vakttyper' },
    { key: 'ettermiddag',  group: 'vakttyper' },
    { key: 'before_6',     group: 'vakttyper' },
    { key: 'tidlig_6_8',   group: 'vakttyper' },
    { key: 'tidlig_8_12',  group: 'vakttyper' },
    { key: 'helgetimer',   group: 'helg' },
    { key: 'helgedager',   group: 'helg' },
    { key: 'natt_helg',    group: 'helg' },
];

const GROUP_HUE = { vakttyper: 214, helg: 142 };

// Shift class from start hour only — schedule data has no end time.
const CLASS_TO_VAR = {
    'night-early': '--color-shift-night-early',
    morning:       '--color-shift-morning',
    midday:        '--color-shift-midday',
    afternoon:     '--color-shift-afternoon',
    evening:       '--color-shift-evening',
    day_off:       '--color-shift-day-off',
};
const WHITE_TEXT_CLASSES = new Set(['morning', 'midday', 'evening']);

const DAY_LABELS = ['Man', 'Tir', 'Ons', 'Tor', 'Fre', 'Lør', 'Søn'];

// ── Helpers ──────────────────────────────────────────────────────────────────

function shiftClass(tidStr) {
    if (!tidStr) return 'day_off';
    const h = parseInt(tidStr.split(':')[0], 10);
    if (h < 6)  return 'night-early';
    if (h < 8)  return 'morning';
    if (h < 12) return 'midday';
    if (h < 17) return 'afternoon';
    return 'evening';
}

function sortedData(rawLabels, rawValues, sortMode) {
    const zipped = rawLabels.map((l, i) => ({ l, v: rawValues[i] }));
    if (sortMode === 'alpha') {
        zipped.sort((a, b) => a.l.localeCompare(b.l, 'nb'));
    } else if (sortMode === 'asc') {
        zipped.sort((a, b) => a.v - b.v);
    } else {
        zipped.sort((a, b) => b.v - a.v);
    }
    return { lbls: zipped.map(x => x.l), vals: zipped.map(x => x.v) };
}

function destroyChart(id) {
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

// Replace the canvas so Chart.js gets a clean slate (no stale dimensions).
function freshCanvas(wrapId, canvasId) {
    const wrap = document.getElementById(wrapId);
    if (!wrap) return [null, null];
    const old = document.getElementById(canvasId);
    if (old) old.remove();
    const canvas = document.createElement('canvas');
    canvas.id = canvasId;
    wrap.appendChild(canvas);
    return [wrap, canvas];
}

function buildScheduleTableHTML(sched) {
    let html = '<div style="overflow-x:auto"><table class="table table-sm table-bordered mb-0" style="table-layout:fixed;width:100%">';
    html += '<thead class="table-light"><tr><th style="width:2.4rem"></th>';
    DAY_LABELS.forEach(d => { html += `<th class="text-center" style="font-size:.75rem">${d}</th>`; });
    html += '</tr></thead><tbody>';
    for (let linje = 1; linje <= 6; linje++) {
        const row = sched[String(linje)] || {};
        html += `<tr><td class="fw-semibold text-secondary align-middle text-center" style="font-size:.72rem;border:1px solid #555">L${linje}</td>`;
        for (let dag = 1; dag <= 7; dag++) {
            const cell = row[String(dag)] || {};
            const tid = cell.tid || '';
            const dg  = cell.dg  || '';
            const cls = shiftClass(tid);
            const bgVar = CLASS_TO_VAR[cls];
            const bgStyle = bgVar ? `background-color:var(${bgVar});` : '';
            const fgStyle = WHITE_TEXT_CLASSES.has(cls) ? 'color:#fff;' : '';
            html += `<td class="${cls} text-center align-middle" style="${bgStyle}${fgStyle}padding:.15rem .2rem;border:1px solid #555;overflow:hidden">`;
            if (dg) html += `<div style="font-size:.62rem;line-height:1.1;opacity:.85">${dg}</div>`;
            html += `<div style="font-size:.72rem;line-height:1.2">${tid || '<span style="opacity:.3">·</span>'}</div>`;
            html += '</td>';
        }
        html += '</tr>';
    }
    html += '</tbody></table></div>';
    return html;
}

// ── Favorites ────────────────────────────────────────────────────────────────

function updateFavButton(turnusName) {
    const icon = document.getElementById('modal-fav-icon');
    const btn  = document.getElementById('modal-fav-btn');
    if (!icon || !btn) return;
    const isFav = favorites.has(turnusName);
    icon.className  = isFav ? 'bi bi-star-fill text-warning' : 'bi bi-star text-secondary';
    icon.style.fontSize = '1.35rem';
    btn.title = isFav ? 'Fjern fra favoritter' : 'Legg til favoritter';
}

function toggleFavorite() {
    if (!currentModalTurnus) return;
    const isFav = favorites.has(currentModalTurnus);
    const btn = document.getElementById('modal-fav-btn');
    if (btn) btn.disabled = true;

    apiFetch('/api/toggle_favorite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shift_title: currentModalTurnus, favorite: !isFav }),
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                favorites = new Set(data.favorites);
                updateFavButton(currentModalTurnus);
            }
        })
        .catch(err => console.error('Favorite toggle failed:', err))
        .finally(() => { if (btn) btn.disabled = false; });
}

// ── Turnus detail modal ──────────────────────────────────────────────────────

function showTurnusModal(turnusName) {
    currentModalTurnus = turnusName;
    const idx = turnusLabels.indexOf(turnusName);

    document.getElementById('turnusModalLabel').textContent = turnusName;
    updateFavButton(turnusName);
    document.getElementById('modal-fav-btn').onclick = toggleFavorite;

    const STATS = [
        { key: 'shift_cnt',           label: 'Dagsverk' },
        { key: 'natt',                label: 'Natt' },
        { key: 'tidlig',              label: 'Tidlig' },
        { key: 'ettermiddag',         label: 'Ettermiddag' },
        { key: 'helgetimer',          label: 'Helgetimer' },
        { key: 'helgedager',          label: 'Helgedager' },
        { key: 'natt_helg',           label: 'Natt helg' },
        { key: 'avg_shift_hours',     label: 'Snitt timer' },
        { key: 'longest_work_streak', label: 'Lengste rekke' },
        { key: 'longest_off_streak',  label: 'Lengste fri' },
        { key: 'afternoons_in_row',   label: 'Etm. på rad' },
    ];

    let html = '<div class="d-flex flex-wrap gap-2 mb-3">';
    STATS.forEach(({ key, label }) => {
        const val = idx >= 0 ? (metricsData[key] || [])[idx] : undefined;
        if (val !== undefined) {
            html += `<div class="border rounded text-center px-2 py-1" style="min-width:4.5rem">` +
                    `<div class="text-secondary" style="font-size:.68rem;line-height:1.2">${label}</div>` +
                    `<div class="fw-bold" style="font-size:1rem;line-height:1.4">${val}</div>` +
                    `</div>`;
        }
    });
    html += '</div>';

    html += '<p class="text-secondary mb-2" style="font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Turnusskjema</p>';
    html += buildScheduleTableHTML(scheduleData[turnusName] || {});

    document.getElementById('turnusModalBody').innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('turnusModal')).show();
}

// ── Heatmap ──────────────────────────────────────────────────────────────────

function makeHeatmap() {
    const tbody = document.getElementById('heatmap-tbody');
    if (!tbody) return;

    const colMaxes = {};
    HEATMAP_COLS.forEach(col => {
        const arr = metricsData[col.key] || [];
        colMaxes[col.key] = arr.length ? Math.max(...arr) : 1;
    });

    tbody.innerHTML = '';
    turnusLabels.forEach(label => {
        const origIdx = turnusLabels.indexOf(label);
        const tr = document.createElement('tr');
        tr.dataset.turnus = label;
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', () => showTurnusModal(label));

        const tdName = document.createElement('td');
        tdName.className = 'turnus-name text-nowrap';
        tdName.textContent = label;
        tr.appendChild(tdName);

        HEATMAP_COLS.forEach((col, colIdx) => {
            const raw   = origIdx >= 0 ? ((metricsData[col.key] || [])[origIdx] ?? 0) : 0;
            const ratio = raw / (colMaxes[col.key] || 1);
            const hue   = GROUP_HUE[col.group] || 214;
            const sat   = Math.round(ratio * 65);
            const lgt   = Math.round(96 - ratio * 44);

            const td = document.createElement('td');
            td.className    = 'hm-cell' + (colIdx === 6 ? ' hm-border-start' : '');
            td.dataset.key  = col.key;
            td.dataset.val  = raw;
            td.style.backgroundColor = `hsl(${hue}, ${sat}%, ${lgt}%)`;
            td.style.color  = ratio > 0.58 ? '#fff' : '#222';
            td.textContent  = typeof raw === 'number' && raw % 1 !== 0 ? raw.toFixed(1) : raw;
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });
}

function initHeatmapSort() {
    let sortKey = null;
    let sortDir = 'desc';
    document.querySelectorAll('.hm-th').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            sortDir = sortKey === key ? (sortDir === 'desc' ? 'asc' : 'desc') : 'desc';
            sortKey = key;
            document.querySelectorAll('.hm-th').forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
            th.classList.add('sort-' + sortDir);
            const tbody = document.getElementById('heatmap-tbody');
            Array.from(tbody.querySelectorAll('tr'))
                .sort((a, b) => {
                    const aV = parseFloat(a.querySelector(`[data-key="${key}"]`)?.dataset.val || '0');
                    const bV = parseFloat(b.querySelector(`[data-key="${key}"]`)?.dataset.val || '0');
                    return sortDir === 'desc' ? bV - aV : aV - bV;
                })
                .forEach(row => tbody.appendChild(row));
        });
    });
}

// ── Charts ───────────────────────────────────────────────────────────────────

function makeBarChart(key, labelsArr, valuesArr, color) {
    const canvasId = 'chart-' + key;
    const wrapId   = 'wrap-'  + key;
    destroyChart(canvasId);
    const [wrap, canvas] = freshCanvas(wrapId, canvasId);
    if (!wrap) return;

    const count    = labelsArr.length;
    const canvasH  = Math.max(count * 26 + 20, 120);
    const maxWrapH = 520;
    wrap.style.maxHeight  = maxWrapH + 'px';
    wrap.style.overflowY  = canvasH > maxWrapH ? 'auto' : 'hidden';
    wrap.style.overflowX  = 'hidden';
    canvas.style.height   = canvasH + 'px';
    canvas.style.width    = '100%';
    canvas.height         = canvasH;

    charts[canvasId] = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labelsArr,
            datasets: [{
                data: valuesArr,
                backgroundColor: color + '33',
                borderColor:     color + 'cc',
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false,
                barPercentage: 0.75,
                categoryPercentage: 0.85,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            onClick: (_e, elements) => {
                if (elements.length > 0) showTurnusModal(labelsArr[elements[0].index]);
            },
            onHover: (_e, elements, chart) => {
                chart.canvas.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid:  { color: 'rgba(0,0,0,0.06)' },
                    ticks: { font: { size: 11 } },
                },
                y: {
                    ticks: {
                        autoSkip: false,
                        font: { size: 12 },
                        padding: 4,
                        callback: function (v) {
                            const lbl = this.getLabelForValue(v);
                            return lbl.length > 22 ? lbl.slice(0, 21) + '…' : lbl;
                        },
                    },
                    grid: { display: false },
                },
            },
            plugins: {
                legend:  { display: false },
                tooltip: { callbacks: { title: items => items[0]?.label || '' } },
            },
        },
    });
}

function makeStackedBar(canvasId, wrapId, labelsArr, datasets, isPercent) {
    destroyChart(canvasId);
    const [wrap, canvas] = freshCanvas(wrapId, canvasId);
    if (!wrap) return;

    const count    = labelsArr.length;
    const canvasH  = Math.max(count * 26 + 20, 120);
    const maxWrapH = 520;
    wrap.style.maxHeight  = maxWrapH + 'px';
    wrap.style.overflowY  = canvasH > maxWrapH ? 'auto' : 'hidden';
    wrap.style.overflowX  = 'hidden';
    canvas.style.height   = canvasH + 'px';
    canvas.style.width    = '100%';
    canvas.height         = canvasH;

    charts[canvasId] = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: { labels: labelsArr, datasets },
        options: {
            indexAxis: 'y',
            responsive: false,
            maintainAspectRatio: false,
            animation: false,
            onClick: (_e, elements) => {
                if (elements.length > 0) showTurnusModal(labelsArr[elements[0].index]);
            },
            onHover: (_e, elements, chart) => {
                chart.canvas.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            },
            scales: {
                x: {
                    stacked: true,
                    beginAtZero: true,
                    ...(isPercent ? { max: 100 } : {}),
                    grid:  { color: 'rgba(0,0,0,0.06)' },
                    ticks: { font: { size: 11 }, ...(isPercent ? { callback: v => v + '%' } : {}) },
                },
                y: {
                    stacked: true,
                    ticks: { autoSkip: false, font: { size: 12 }, padding: 4 },
                    grid:  { display: false },
                },
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 11 }, padding: 12 },
                },
                tooltip: {
                    callbacks: {
                        title: items => items[0]?.label || '',
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw}${isPercent ? '%' : ''}`,
                    },
                },
            },
        },
    });
}

function renderVaktprofil() {
    const KEYS   = ['natt', 'tidlig', 'ettermiddag'];
    const COLORS = ['#1e3a5f', '#3b82f6', '#f87171'];
    const LBLS   = ['Natt', 'Tidlig', 'Ettermiddag'];

    const { lbls } = sortedData(turnusLabels, metricsData['natt'] || [], currentSort);
    const totals = lbls.map(lbl => {
        const i = turnusLabels.indexOf(lbl);
        return KEYS.reduce((s, k) => s + ((metricsData[k] || [])[i] || 0), 0);
    });
    const datasets = KEYS.map((k, ki) => ({
        label: LBLS[ki],
        data: lbls.map((lbl, ri) => {
            const i = turnusLabels.indexOf(lbl);
            return Math.round(((metricsData[k] || [])[i] || 0) / (totals[ri] || 1) * 100);
        }),
        backgroundColor: COLORS[ki] + 'cc',
        borderColor:     COLORS[ki],
        borderWidth: 1,
        borderRadius: 2,
        borderSkipped: false,
    }));
    makeStackedBar('chart-vaktprofil', 'wrap-vaktprofil', lbls, datasets, true);
}

function renderHelgeprofil() {
    if (!(metricsData['helgetimer_dagtid'] || []).length) return;
    const { lbls } = sortedData(turnusLabels, metricsData['helgetimer'] || [], currentSort);
    const datasets = [
        {
            label: 'Dagtid (lør/søn før 14)',
            data: lbls.map(lbl => (metricsData['helgetimer_dagtid'] || [])[turnusLabels.indexOf(lbl)] || 0),
            backgroundColor: '#6ee7b7cc',
            borderColor: '#10b981',
            borderWidth: 1, borderRadius: 2, borderSkipped: false,
        },
        {
            label: 'Kveld/natt (fre 17+, lør/søn etter 14)',
            data: lbls.map(lbl => (metricsData['helgetimer_ettermiddag'] || [])[turnusLabels.indexOf(lbl)] || 0),
            backgroundColor: '#065f46cc',
            borderColor: '#064e3b',
            borderWidth: 1, borderRadius: 2, borderSkipped: false,
        },
    ];
    makeStackedBar('chart-helgeprofil', 'wrap-helgeprofil', lbls, datasets, false);
}

function renderRytmescore() {
    const rawScores = turnusLabels.map((_, i) => {
        const off  = (metricsData.longest_off_streak  || [])[i] || 0;
        const work = (metricsData.longest_work_streak || [])[i] || 1;
        return Math.round(off / work * 100) / 100;
    });
    const { lbls, vals } = sortedData(turnusLabels, rawScores, currentSort);
    makeBarChart('rytmescore', lbls, vals, '#f59e0b');
}

function renderSectionCharts() {
    SECTIONS.forEach(section => {
        section.metrics.forEach(({ key }) => {
            const rawArr = metricsData[key] || [];
            if (!rawArr.length) return;
            const { lbls, vals } = sortedData(turnusLabels, rawArr, currentSort);
            makeBarChart(key, lbls, vals, section.color);
        });
    });
    renderVaktprofil();
    renderHelgeprofil();
    renderRytmescore();
}

// ── Highlight strip ──────────────────────────────────────────────────────────

const sundayNightVals = turnusLabels.map(name => {
    let count = 0;
    const sched = scheduleData[name] || {};
    for (let linje = 1; linje <= 6; linje++) {
        const tid = ((sched[String(linje)] || {})[String(7)] || {}).tid || '';
        if (tid && parseInt(tid.split(':')[0], 10) >= 17) count++;
    }
    return count;
});

const RECORDS = [
    { label: 'Flest nattevakter',  key: 'natt',               dir: 'max', icon: '🌙' },
    { label: 'Minst helgetimer',   key: 'helgetimer',          dir: 'min', icon: '☀️', nonzero: true },
    { label: 'Flest helgedager',   key: 'helgedager',          dir: 'max', icon: '📅' },
    { label: 'Lengste fri',        key: 'longest_off_streak',  dir: 'max', icon: '🏖️' },
    { label: 'Flest ettermiddager',key: 'ettermiddag',         dir: 'max', icon: '🌆' },
    { label: 'Færrest tidlig',     key: 'tidlig',              dir: 'min', icon: '⏰', nonzero: true },
    { label: 'Flest natt til mandag', vals: sundayNightVals,   dir: 'max', icon: '🌃' },
];

function renderHighlights() {
    const strip = document.getElementById('highlight-strip');
    if (!strip) return;
    strip.innerHTML = '';

    RECORDS.forEach(rec => {
        const arr = rec.vals || metricsData[rec.key] || [];
        if (!arr.length) return;

        let bestIdx;
        if (rec.dir === 'max') {
            bestIdx = arr.indexOf(Math.max(...arr));
        } else {
            const candidates = rec.nonzero
                ? arr.map((v, i) => v > 0 ? i : -1).filter(i => i >= 0)
                : arr.map((_, i) => i);
            if (!candidates.length) return;
            bestIdx = candidates.reduce((b, i) => arr[i] < arr[b] ? i : b, candidates[0]);
        }

        const badge = document.createElement('span');
        badge.className = 'record-badge';
        badge.innerHTML =
            `<span class="record-icon">${rec.icon}</span>` +
            `<span>${rec.label}:</span>` +
            `<a href="#" class="record-value text-decoration-none modal-turnus-link"` +
            ` data-turnus="${turnusLabels[bestIdx]}">${turnusLabels[bestIdx]}</a>` +
            `<span class="text-secondary">— ${arr[bestIdx]}</span>`;
        strip.appendChild(badge);
    });
}

// ── Weekday grid ─────────────────────────────────────────────────────────────

function colorWeekdayGrid() {
    const colMaxes = Array(7).fill(0);
    document.querySelectorAll('.wd-cell').forEach(cell => {
        const col = parseInt(cell.dataset.col, 10);
        const cnt = parseInt(cell.dataset.count, 10);
        if (cnt > colMaxes[col]) colMaxes[col] = cnt;
    });
    document.querySelectorAll('.wd-cell').forEach(cell => {
        const col   = parseInt(cell.dataset.col, 10);
        const cnt   = parseInt(cell.dataset.count, 10);
        const ratio = cnt / (colMaxes[col] || 1);
        const pill  = cell.querySelector('.wd-pill');
        if (pill) {
            pill.style.backgroundColor = `hsl(142, ${Math.round(ratio * 55)}%, ${Math.round(95 - ratio * 38)}%)`;
            pill.style.color = ratio > 0.65 ? '#fff' : 'inherit';
        }
    });
}

function initWeekdaySort() {
    let sortCol = null;
    let sortDir = 'desc';
    document.querySelectorAll('.wd-th').forEach(th => {
        th.addEventListener('click', () => {
            const col = parseInt(th.dataset.col, 10);
            sortDir = sortCol === col ? (sortDir === 'desc' ? 'asc' : 'desc') : 'desc';
            sortCol = col;
            document.querySelectorAll('.wd-th').forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
            th.classList.add('sort-' + sortDir);
            const tbody = document.getElementById('weekday-tbody');
            Array.from(tbody.querySelectorAll('tr'))
                .sort((a, b) => {
                    const aV = parseInt(a.querySelector(`.wd-cell[data-col="${col}"]`)?.dataset.count || '0', 10);
                    const bV = parseInt(b.querySelector(`.wd-cell[data-col="${col}"]`)?.dataset.count || '0', 10);
                    return sortDir === 'desc' ? bV - aV : aV - bV;
                })
                .forEach(row => tbody.appendChild(row));
        });
    });
}

// ── Innplassering schedule accordion ────────────────────────────────────────

document.querySelectorAll('.inn-row').forEach(row => {
    row.addEventListener('click', () => {
        const schedRow = document.getElementById(row.dataset.target);
        const chevron  = row.querySelector('.inn-chevron');
        const isOpen   = schedRow.style.display !== 'none';

        if (isOpen) {
            schedRow.style.display = 'none';
            if (chevron) chevron.style.transform = '';
        } else {
            const body = schedRow.querySelector('.inn-schedule-body');
            if (body && !body.dataset.rendered) {
                const sched = (innSchedules[String(row.dataset.turnusSetId)] || {})[row.dataset.shiftTitle] || {};
                body.innerHTML = buildScheduleTableHTML(sched);
                body.dataset.rendered = '1';
            }
            schedRow.style.display = '';
            if (chevron) chevron.style.transform = 'rotate(90deg)';
        }
    });
});

// ── Global event delegation ──────────────────────────────────────────────────

const sortSelect = document.getElementById('global-sort');
if (sortSelect) {
    sortSelect.addEventListener('change', () => {
        currentSort = sortSelect.value;
        renderSectionCharts();
    });
}

document.addEventListener('click', e => {
    const link = e.target.closest('.modal-turnus-link');
    if (link) { e.preventDefault(); showTurnusModal(link.dataset.turnus); }
});

// ── Init ─────────────────────────────────────────────────────────────────────

makeHeatmap();
initHeatmapSort();
renderHighlights();
renderSectionCharts();
colorWeekdayGrid();
initWeekdaySort();
