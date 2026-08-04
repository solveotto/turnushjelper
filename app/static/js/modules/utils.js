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

        if (!printContents) return;  // nothing to print

        Utils._printHtml(printContents);
    }

    // Print an HTML fragment without destroying the live page.
    //
    // The old approach swapped document.body.innerHTML, called window.print(),
    // then restored it synchronously. That only works because window.print()
    // BLOCKS on desktop. On mobile browsers (iOS Safari, Chrome Android)
    // window.print() returns immediately and renders the print snapshot
    // asynchronously — so the synchronous restore had already put the full web
    // page back before the snapshot was taken, and the phone printed the page
    // instead of the shifts. Instead we append a hidden print root, hide
    // everything else via @media print, and clean up on afterprint so nothing
    // races the async mobile print.
    static _printHtml(html) {
        // Drop any leftover root from a run whose afterprint never fired.
        document.getElementById('print-root')?.remove();

        const printRoot = document.createElement('div');
        printRoot.id = 'print-root';
        printRoot.innerHTML = html;
        document.body.appendChild(printRoot);
        document.body.classList.add('is-printing');

        const mql = window.matchMedia ? window.matchMedia('print') : null;
        let done = false;
        const cleanup = () => {
            if (done) return;
            done = true;
            printRoot.remove();
            document.body.classList.remove('is-printing');
            window.removeEventListener('afterprint', cleanup);
            mql?.removeEventListener?.('change', onMediaChange);
        };
        const onMediaChange = (e) => { if (!e.matches) cleanup(); };

        window.addEventListener('afterprint', cleanup);
        mql?.addEventListener?.('change', onMediaChange);

        window.print();
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

/**
 * Escape a value for interpolation into an HTML template literal.
 *
 * Use on anything that came from server JSON (turnus names, shift times,
 * dagsverk codes, metric values) before it goes into an `innerHTML` string.
 * Module-local constants — DAY_LABELS, the RECORDS icons/labels — don't need
 * it and are left alone.
 *
 * Quotes are escaped too, so the result is safe inside a quoted attribute
 * (e.g. data-turnus="${escapeHtml(name)}"), not just in text position.
 */
export function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

window.escapeHtml = escapeHtml;
