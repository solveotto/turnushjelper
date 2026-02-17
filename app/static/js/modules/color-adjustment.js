// Color Adjustment Module
// Handles the color customization system for shift tables
// Uses shared classifier from shift-classifier.js for consistent categorization

import { classifyCell, SHIFT_TYPES } from './shift-classifier.js';

export class ColorAdjustment {
    constructor() {
        this.defaultSettings = {
            nightEarly: { color: '#1B3A6B', label: 'Før 06:00' },
            morning:    { color: '#4A90D9', label: '06:00–07:59' },
            midday:     { color: '#87CEEB', label: '08:00–11:59' },
            afternoon:  { color: '#FF9999', label: 'Kveldsvakt' },
            evening:    { color: '#9B59B6', label: 'Nattevakt' },
            dayoff:     { color: '#4ADE80', label: 'Fridag' },
            hdag:       { color: '#FCD34D', label: 'Helligdag' }
        };

        // Map from classifier SHIFT_TYPES to settings keys
        this.typeToSettingKey = {
            [SHIFT_TYPES.NIGHT_EARLY]: { key: 'nightEarly', needsWhiteText: true },
            [SHIFT_TYPES.MORNING]:     { key: 'morning',    needsWhiteText: false },
            [SHIFT_TYPES.MIDDAY]:      { key: 'midday',     needsWhiteText: false },
            [SHIFT_TYPES.AFTERNOON]:   { key: 'afternoon',  needsWhiteText: false },
            [SHIFT_TYPES.EVENING]:     { key: 'evening',    needsWhiteText: true },
            [SHIFT_TYPES.DAY_OFF]:     { key: 'dayoff',     needsWhiteText: false },
            [SHIFT_TYPES.HOLIDAY]:     { key: 'hdag',       needsWhiteText: false }
        };

        this.init();
    }

    init() {
        document.addEventListener('DOMContentLoaded', () => {
            // Check if we're on the turnusliste page
            const colorPanel = document.querySelector('#apply-colors');
            if (!colorPanel) return;

            this.setupEventListeners();
            this.initializeColorInputs();
            this.applyColorsToTable();
            console.log('Color adjustment system initialized');
        });
    }

    setupEventListeners() {
        // Apply button
        const applyButton = document.getElementById('apply-colors');
        if (applyButton) {
            applyButton.addEventListener('click', () => this.handleApplyColors());
        }

        // Reset button
        const resetButton = document.getElementById('reset-colors');
        if (resetButton) {
            resetButton.addEventListener('click', () => this.handleResetColors());
        }
    }

    loadColorSettings() {
        try {
            const saved = localStorage.getItem('shiftColorSettings');
            if (saved) {
                const parsed = JSON.parse(saved);
                // Migration: if old keys are present, clear and return defaults
                if (parsed.early || parsed.earlylate || parsed.earlybefore6 || parsed.late || parsed.night) {
                    localStorage.removeItem('shiftColorSettings');
                    return { ...this.defaultSettings };
                }
                return { ...this.defaultSettings, ...parsed };
            }
        } catch (error) {
            console.warn('Error loading color settings:', error);
        }
        return { ...this.defaultSettings };
    }

    saveColorSettings(settings) {
        try {
            localStorage.setItem('shiftColorSettings', JSON.stringify(settings));
            console.log('Color settings saved:', settings);
        } catch (error) {
            console.error('Error saving color settings:', error);
        }
    }

    applyColorsToTable() {
        const settings = this.loadColorSettings();

        // Remove existing color classes
        const tds = document.querySelectorAll('td[id="cell"]');

        tds.forEach(td => {
            td.classList.remove('night-early', 'morning', 'midday', 'afternoon', 'evening', 'day_off', 'h-dag');
            td.style.backgroundColor = '';
            td.style.color = '';
        });

        // Apply new colors based on settings
        tds.forEach(td => this.colorCell(td, settings));
    }

    colorCell(td, settings) {
        const timeTextElement = td.querySelector('.time-text');
        if (!timeTextElement) return;

        const timeText = timeTextElement.textContent;
        const customTextElement = td.querySelector('.custom-text');
        const customText = customTextElement ? customTextElement.textContent : '';

        const shiftType = classifyCell(timeText, customText);
        if (!shiftType) return;

        const mapping = this.typeToSettingKey[shiftType];
        if (!mapping) return;

        td.style.backgroundColor = settings[mapping.key].color;
        if (mapping.needsWhiteText) {
            td.style.color = '#fff';
        }
    }

    initializeColorInputs() {
        const settings = this.loadColorSettings();

        try {
            const colorInputs = {
                'nightearly-color': settings.nightEarly.color,
                'morning-color': settings.morning.color,
                'midday-color': settings.midday.color,
                'afternoon-color': settings.afternoon.color,
                'evening-color': settings.evening.color,
                'dayoff-color': settings.dayoff.color,
                'hdag-color': settings.hdag.color
            };

            Object.entries(colorInputs).forEach(([id, value]) => {
                const input = document.getElementById(id);
                if (input) input.value = value;
            });

            console.log('Color inputs initialized with settings:', settings);
        } catch (error) {
            console.error('Error initializing color inputs:', error);
        }
    }

    handleApplyColors() {
        try {
            const newSettings = {
                nightEarly: {
                    color: document.getElementById('nightearly-color')?.value || this.defaultSettings.nightEarly.color,
                    label: this.defaultSettings.nightEarly.label
                },
                morning: {
                    color: document.getElementById('morning-color')?.value || this.defaultSettings.morning.color,
                    label: this.defaultSettings.morning.label
                },
                midday: {
                    color: document.getElementById('midday-color')?.value || this.defaultSettings.midday.color,
                    label: this.defaultSettings.midday.label
                },
                afternoon: {
                    color: document.getElementById('afternoon-color')?.value || this.defaultSettings.afternoon.color,
                    label: this.defaultSettings.afternoon.label
                },
                evening: {
                    color: document.getElementById('evening-color')?.value || this.defaultSettings.evening.color,
                    label: this.defaultSettings.evening.label
                },
                dayoff: {
                    color: document.getElementById('dayoff-color')?.value || this.defaultSettings.dayoff.color,
                    label: this.defaultSettings.dayoff.label
                },
                hdag: {
                    color: document.getElementById('hdag-color')?.value || this.defaultSettings.hdag.color,
                    label: this.defaultSettings.hdag.label
                }
            };

            this.saveColorSettings(newSettings);
            this.applyColorsToTable();

            this.showButtonFeedback('apply-colors', 'Farger brukt!', 'btn-success');
            console.log('Colors applied successfully');
        } catch (error) {
            console.error('Error applying colors:', error);
            alert('Feil ved bruk av farger. Sjekk konsollen for detaljer.');
        }
    }

    handleResetColors() {
        if (confirm('Er du sikker på at du vil tilbakestille alle fargeinnstillinger?')) {
            try {
                localStorage.removeItem('shiftColorSettings');
                this.initializeColorInputs();
                this.applyColorsToTable();

                this.showButtonFeedback('reset-colors', 'Reset!', 'btn-success');
                console.log('Colors reset to defaults');
            } catch (error) {
                console.error('Error resetting colors:', error);
                alert('Feil ved tilbakestilling av farger. Sjekk konsollen for detaljer.');
            }
        }
    }

    showButtonFeedback(buttonId, message, successClass) {
        const button = document.getElementById(buttonId);
        if (!button) return;

        const originalText = button.innerHTML;
        const originalClass = button.className;

        button.innerHTML = `<i class="bi bi-check-circle-fill"></i> ${message}`;
        button.className = button.className.replace(/btn-\w+/, successClass);

        setTimeout(() => {
            button.innerHTML = originalText;
            button.className = originalClass;
        }, 2000);
    }
}
