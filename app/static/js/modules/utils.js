// Utilities Module
// Shared utility functions

import { classifyCell, SHIFT_TYPES } from './shift-classifier.js';

const SHIFT_STYLE_MAP = {
    [SHIFT_TYPES.NIGHT_EARLY]: { cls: 'night-early', key: 'nightEarly', whiteText: true },
    [SHIFT_TYPES.MORNING]:     { cls: 'morning',     key: 'morning',    whiteText: false },
    [SHIFT_TYPES.MIDDAY]:      { cls: 'midday',      key: 'midday',     whiteText: false },
    [SHIFT_TYPES.AFTERNOON]:   { cls: 'afternoon',   key: 'afternoon',  whiteText: false },
    [SHIFT_TYPES.EVENING]:     { cls: 'evening',     key: 'evening',    whiteText: true },
    [SHIFT_TYPES.DAY_OFF]:     { cls: 'day_off',     key: 'dayoff',     whiteText: false },
    [SHIFT_TYPES.HOLIDAY]:     { cls: 'h-dag',       key: 'hdag',       whiteText: false }
};

const DEFAULT_COLORS = {
    nightEarly: '#1B3A6B',
    morning:    '#4A90D9',
    midday:     '#87CEEB',
    afternoon:  '#FF9999',
    evening:    '#9B59B6',
    dayoff:     '#4ADE80',
    hdag:       '#FCD34D'
};

export class Utils {
    static disableSubmitButton(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerText = 'Submitting...';
        }
        return true;  // Ensure the form is submitted
    }

    static _applyColorsToRoot(root) {
        let customSettings = null;
        try {
            const saved = localStorage.getItem('shiftColorSettings');
            if (saved) {
                const parsed = JSON.parse(saved);
                if (!parsed.early && !parsed.earlylate && !parsed.earlybefore6 && !parsed.late && !parsed.night) {
                    customSettings = parsed;
                }
            }
        } catch (e) { /* ignore */ }

        root.querySelectorAll('td[id="cell"]').forEach(td => {
            const timeEl = td.querySelector('.time-text');
            if (!timeEl) return;
            const timeText = timeEl.textContent;
            const customEl = td.querySelector('.custom-text');
            const customText = customEl ? customEl.textContent : '';
            const shiftType = classifyCell(timeText, customText);
            if (!shiftType) return;
            const mapping = SHIFT_STYLE_MAP[shiftType];
            if (!mapping) return;

            if (customSettings) {
                const entry = customSettings[mapping.key];
                const color = (entry && entry.color) ? entry.color : DEFAULT_COLORS[mapping.key];
                td.style.backgroundColor = color;
                if (mapping.whiteText) td.style.color = '#fff';
            } else {
                td.classList.add(mapping.cls);
            }
        });
    }

    static printTables() {
        var printContents = '';
        var items = document.querySelectorAll('.list-group-item');

        items.forEach(function(container) {
            // Get table HTML from live DOM or from unrendered lazy template
            var tableHTML = '';
            var liveTable = container.querySelector('table');
            if (liveTable) {
                tableHTML = liveTable.outerHTML;
            } else {
                var tmpl = container.querySelector('template[data-lazy-table]');
                if (tmpl) {
                    var tmp = document.createElement('div');
                    tmp.appendChild(tmpl.content.cloneNode(true));
                    Utils._applyColorsToRoot(tmp);
                    var clonedTable = tmp.querySelector('table');
                    if (clonedTable) tableHTML = clonedTable.outerHTML;
                }
            }

            if (!tableHTML) return;  // not a turnus row

            var nameElement = container.querySelector('.t-name');
            if (!nameElement) return;
            var name = nameElement.innerText;

            var numberElement = container.querySelector('.t-num');
            var number = numberElement ? numberElement.innerText + ' - ' : '';

            var dataFeltElement = container.querySelector('.data-felt');
            var dataFelt = dataFeltElement ? dataFeltElement.outerHTML : '';

            printContents += '<div class="print-frame"><h4>' + number + name + '</h4>' + tableHTML + dataFelt + '</div>';
        });

        var originalContents = document.body.innerHTML;
        document.body.innerHTML = printContents;
        window.print();
        document.body.innerHTML = originalContents;
        window.app?.modules?.lazyTables?.reinit();
    }
}

export class ScrollPosition {
    constructor() {
        this.indexRoute = '/';
        this.specificRoute = window.location.pathname;
        this.init();
    }

    init() {
        if (window.location.pathname === this.indexRoute) {
            this.setupScrollSaving();
            this.restoreScrollPosition();
        }
    }

    setupScrollSaving() {
        // Save the scroll position before the user navigates away
        window.addEventListener('beforeunload', () => {
            localStorage.setItem('scrollPosition', window.scrollY);
        });
    }

    restoreScrollPosition() {
        // Restore the scroll position after the page has fully loaded
        window.onload = () => {
            setTimeout(() => {
                const savedPosition = localStorage.getItem('scrollPosition-' + this.specificRoute);
                if (savedPosition) {
                    window.scrollTo(0, parseInt(savedPosition));
                }
            }, 100);  // Delay restoration slightly to ensure content has loaded
        };
    }
}

// Make printTables available globally for backward compatibility
window.printTables = Utils.printTables;
window.disableSubmitButton = Utils.disableSubmitButton;
