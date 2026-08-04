// Utilities Module
// Shared utility functions
//
// Printing lives in print-utils.js only. This module used to carry a second
// copy of printTables()/_printHtml() and assign window.printTables as well;
// which copy survived came down to ES module evaluation order, so a fix
// applied to one file could leave the running one untouched.

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
