// Utilities Module
// Shared utility functions

import { classifyCell } from './shift-classifier.js';

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
        root.querySelectorAll('td[id="cell"]').forEach(td => {
            const timeEl = td.querySelector('.time-text');
            if (!timeEl) return;
            const timeText = timeEl.textContent;
            const customEl = td.querySelector('.custom-text');
            const customText = customEl ? customEl.textContent : '';
            const shiftType = classifyCell(timeText, customText);
            if (shiftType) td.classList.add(shiftType);
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

// Make printTables available globally for backward compatibility
window.printTables = Utils.printTables;
window.disableSubmitButton = Utils.disableSubmitButton;

export function apiFetch(url, options = {}) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...options.headers };
    if (method !== 'GET' && method !== 'HEAD' && csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
    }
    return fetch(url, { ...options, headers }).then(async response => {
        if (response.status === 400) {
            const data = await response.clone().json().catch(() => null);
            if (data?.code === 'csrf_expired') {
                window.location.reload();
                return new Promise(() => {});
            }
        }
        return response;
    });
}

window.apiFetch = apiFetch;
