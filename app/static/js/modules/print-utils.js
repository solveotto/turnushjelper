// Print Utilities Module

import { classifyCell } from './shift-classifier.js';

export class PrintUtils {
    // Apply shift colors to all td[id="cell"] within a detached root element.
    // Used for tables cloned from <template> that haven't been rendered yet.
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
                    PrintUtils._applyColorsToRoot(tmp);
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

        PrintUtils._printHtml(printContents);
    }

    // Print an HTML fragment without destroying the live page.
    //
    // We append a hidden print root holding just the shift tables and hide
    // everything else via @media print. The delicate part is when that state
    // is torn down again.
    //
    // window.print() BLOCKS on desktop, but not on mobile. Chrome on Android
    // returns from it immediately, fires afterprint straight away, and leaves
    // the actual rendering to the Android print framework, which snapshots the
    // page later. So teardown driven by print events — afterprint, or a
    // matchMedia('print') change — runs before the snapshot exists and the
    // tablet prints the live page: with the menu still open, that is a
    // full-screen overlay repeated across every page.
    //
    // Nothing here is torn down on a print event for that reason. #print-root
    // is display:none outside @media print, so leaving it in the document is
    // invisible; we clear it on the user's next interaction, which cannot
    // happen until the print UI has been dismissed.
    static _printHtml(html) {
        // Drop any leftover root from a run the user never interacted after.
        document.getElementById('print-root')?.remove();

        const printRoot = document.createElement('div');
        printRoot.id = 'print-root';
        printRoot.innerHTML = html;
        document.body.appendChild(printRoot);
        document.body.classList.add('is-printing');

        const events = ['pointerdown', 'keydown'];
        const cleanup = () => {
            events.forEach(evt =>
                window.removeEventListener(evt, cleanup, true)
            );
            printRoot.remove();
            document.body.classList.remove('is-printing');
        };
        events.forEach(evt => window.addEventListener(evt, cleanup, true));

        window.print();
    }

    static disableSubmitButton(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerText = 'Submitting...';
        }
        return true;  // Ensure the form is submitted
    }
}

// Make functions available globally for backward compatibility
window.printTables = PrintUtils.printTables;
window.disableSubmitButton = PrintUtils.disableSubmitButton;
