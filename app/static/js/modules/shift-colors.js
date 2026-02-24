// Shift Colors Module
// Applies CSS classes to shift table cells using the shared classifier

import { classifyCell } from './shift-classifier.js';

export class ShiftColors {
    constructor() {
        this.init();
    }

    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.applyShiftColors();
            });
        } else {
            this.applyShiftColors();
        }
    }

    applyShiftColors() {
        // Skip if custom color settings are active (user has configured custom colors)
        if (localStorage.getItem('shiftColorSettings')) {
            return;
        }

        this.colorAllCells();
    }

    colorAllCells() {
        const tds = document.querySelectorAll('td[id="cell"]');
        tds.forEach(td => this.colorCell(td));
    }

    colorCell(td) {
        const timeTextElement = td.querySelector('.time-text');
        if (!timeTextElement) return;

        const timeText = timeTextElement.textContent;
        const customTextElement = td.querySelector('.custom-text');
        const customText = customTextElement ? customTextElement.textContent : '';

        const shiftType = classifyCell(timeText, customText);
        if (shiftType) {
            td.classList.add(shiftType);
        }
    }

    // Apply colors to cells within a scoped root element (used by lazy table loader)
    applyColorsToRoot(root) {
        if (localStorage.getItem('shiftColorSettings')) return;
        root.querySelectorAll('td[id="cell"]').forEach(td => this.colorCell(td));
    }

    // Method to manually trigger color application (useful for dynamic content)
    refresh() {
        this.colorAllCells();
    }

    // Method to clear all color classes
    clearColors() {
        const allClasses = ['night-early', 'morning', 'midday', 'afternoon', 'evening', 'day_off', 'h-dag'];
        document.querySelectorAll('td[id="cell"]').forEach(td => {
            td.classList.remove(...allClasses);
        });
    }
}
