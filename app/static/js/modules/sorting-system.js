// Sorting System Module
// Handles turnusliste sorting functionality

export class SortingSystem {
    constructor() {
        this.originalOrder = [];
        this.currentOrder = [];
        this.init();
    }

    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.initializeSorting();
            });
        } else {
            this.initializeSorting();
        }
    }

    initializeSorting() {
        // Check if we're on the turnusliste page
        const sortingContainer = document.querySelector('#helgetimer-slider');
        if (!sortingContainer) {
            console.log('No sorting container found, skipping sorting initialization');
            return;
        }

        this.initializeOriginalOrder();
        this.setupEventListeners();
        
        // Load and apply saved settings, then sort if any were applied
        if (this.applySavedSettings()) {
            this.sortTurnuser();
        }
        
        // Initialize slider values
        const sliders = document.querySelectorAll('input[type="range"]');
        sliders.forEach(slider => this.updateSliderValue(slider));
    }

    initializeOriginalOrder() {
        const turnusItems = document.querySelectorAll('.list-group-item');
        this.originalOrder = Array.from(turnusItems).map(item => {
            const turnusName = item.querySelector('.t-name').textContent.trim();
            return { element: item, name: turnusName };
        });
        this.currentOrder = [...this.originalOrder];
    }

    getTurnusData() {
        const turnusData = [];
        const turnusItems = document.querySelectorAll('.list-group-item');
        
        turnusItems.forEach((item, index) => {
            const turnusName = item.querySelector('.t-name');
            if (!turnusName) {
                console.warn(`No turnus name found for item ${index}`);
                return;
            }
            
            const name = turnusName.textContent.trim();
            const dataRow = item.querySelector('.data-felt');
            
            if (dataRow) {
                try {
                    // data-felt uses a CSS grid: interleaved <span> label + <b> value pairs.
                    // Order: Dagsverk, Tidlig, Kveld, Natt, Starter før 6, Tidlig 6-8,
                    //        Tidlig 8-12, Snitt t/skift, Helgetimer, Helgtimer dag,
                    //        Lengste fri, Lengste rekke
                    const bs = dataRow.querySelectorAll('b');
                    const shiftCnt   = parseInt(bs[0]?.textContent)   || 0;
                    const tidlig     = parseInt(bs[1]?.textContent)   || 0;
                    const ettermiddag = parseInt(bs[2]?.textContent)  || 0;
                    const natt       = parseInt(bs[3]?.textContent)   || 0;
                    const before6    = parseInt(bs[4]?.textContent)   || 0;
                    const tidlig68   = parseInt(bs[5]?.textContent)   || 0;
                    const tidlig812  = parseInt(bs[6]?.textContent)   || 0;
                    const avgHours   = parseFloat(bs[7]?.textContent) || 0;
                    const helgetimer = parseInt(bs[8]?.textContent)   || 0;
                    // bs[9] = helgetimer_dagtid (not used in sorting)
                    const longestOff    = parseInt(bs[10]?.textContent) || 0;
                    const longestStreak = parseInt(bs[11]?.textContent) || 0;

                    turnusData.push({
                        name: name,
                        element: item,
                        shift_cnt: shiftCnt,
                        tidlig: tidlig,
                        ettermiddag: ettermiddag,
                        natt: natt,
                        helgetimer: helgetimer,
                        before_6: before6,
                        tidlig_6_8: tidlig68,
                        tidlig_8_12: tidlig812,
                        longest_off_streak: longestOff,
                        longest_work_streak: longestStreak,
                        avg_shift_hours: avgHours
                    });
                } catch (error) {
                    console.error(`Error parsing data for turnus ${name}:`, error);
                }
            } else {
                console.warn(`No data-felt found for turnus ${name}`);
            }
        });
        
        return turnusData;
    }

    /**
     * Calculate min/max values for each criterion from the current dataset
     */
    calculateMinMax(turnusData) {
        const criteria = ['helgetimer', 'shift_cnt', 'tidlig', 'natt', 'ettermiddag', 'before_6',
                          'tidlig_6_8', 'tidlig_8_12', 'longest_off_streak', 'longest_work_streak', 'avg_shift_hours'];
        const minMax = {};

        criteria.forEach(key => {
            const values = turnusData.map(t => t[key] || 0);
            minMax[key] = {
                min: Math.min(...values),
                max: Math.max(...values)
            };
        });

        return minMax;
    }

    /**
     * Normalize a value to a 0-1 scale based on min/max
     */
    normalizeValue(value, min, max) {
        if (max === min) return 0.5; // Avoid division by zero
        return (value - min) / (max - min);
    }

    calculateScore(turnus, weights, minMax) {
        let score = 0;

        // For each criteria, calculate contribution based on normalized values and weights
        Object.entries(weights).forEach(([key, weight]) => {
            if (weight === 0) return; // Skip neutral weights

            const dataKey = key;
            const value = turnus[dataKey] || 0;
            const { min, max } = minMax[dataKey] || { min: 0, max: 1 };

            // Normalize to 0-1 scale
            const normalized = this.normalizeValue(value, min, max);

            // Positive weight: higher normalized values get higher scores
            // Negative weight: lower normalized values get higher scores (invert)
            let contribution;
            if (weight > 0) {
                contribution = normalized * Math.abs(weight);
            } else {
                contribution = (1 - normalized) * Math.abs(weight);
            }

            score += contribution;
        });

        return score;
    }

    sortTurnuser() {
        const weights = {
            helgetimer: parseFloat(document.getElementById('helgetimer-slider').value),
            shift_cnt: parseFloat(document.getElementById('shift-cnt-slider').value),
            tidlig: parseFloat(document.getElementById('tidlig-slider').value),
            natt: parseFloat(document.getElementById('natt-slider').value),
            ettermiddag: parseFloat(document.getElementById('ettermiddag-slider').value),
            before_6: parseFloat(document.getElementById('before-6-slider').value),
            tidlig_6_8: parseFloat(document.getElementById('tidlig-6-8-slider').value),
            tidlig_8_12: parseFloat(document.getElementById('tidlig-8-12-slider').value),
            longest_off_streak: parseFloat(document.getElementById('longest-off-slider').value),
            longest_work_streak: parseFloat(document.getElementById('longest-streak-slider').value),
            avg_shift_hours: parseFloat(document.getElementById('avg-hours-slider').value)
        };

        const turnusData = this.getTurnusData();

        if (turnusData.length === 0) {
            console.warn('No turnus data found');
            return;
        }

        // Calculate actual min/max from data for normalization
        const minMax = this.calculateMinMax(turnusData);

        // Calculate scores with normalization
        turnusData.forEach(turnus => {
            turnus.score = this.calculateScore(turnus, weights, minMax);
        });
        
        turnusData.sort((a, b) => b.score - a.score);
        
        // Reorder DOM elements
        const container = document.querySelector('.list-group');
        if (container) {
            turnusData.forEach(turnus => {
                container.appendChild(turnus.element);
            });
        }
        
        // Update current order
        this.currentOrder = turnusData.map(t => ({ element: t.element, name: t.name }));
        
        // Update sorting info display
        this.updateSortingInfo(weights);
    }

    resetOrder() {
        const container = document.querySelector('.list-group');
        this.originalOrder.forEach(turnus => {
            container.appendChild(turnus.element);
        });
        this.currentOrder = [...this.originalOrder];
        
        // Reset all sliders
        const sliders = document.querySelectorAll('input[type="range"]');
        sliders.forEach(slider => {
            slider.value = 0;
            this.updateSliderValue(slider);
        });
        
        // Clear saved settings
        try {
            localStorage.removeItem('turnuslisteSortingSettings');
            console.log('Sorting settings cleared');
        } catch (error) {
            console.error('Error clearing sorting settings:', error);
        }
        
        // Hide sorting info
        const sortingInfo = document.getElementById('sorting-info');
        if (sortingInfo) {
            sortingInfo.style.display = 'none';
        }

        // Clear active-criteria badge on the Sorter button
        const badge = document.getElementById('sorter-active-badge');
        if (badge) {
            badge.textContent = '0';
            badge.classList.add('d-none');
        }
    }

    updateSliderValue(slider) {
        const valueDisplay = document.getElementById(slider.id.replace('-slider', '-value'));
        if (valueDisplay) {
            valueDisplay.textContent = slider.value;
            
            // Update badge color based on value
            if (parseFloat(slider.value) > 0) {
                valueDisplay.className = 'badge bg-success';
            } else if (parseFloat(slider.value) < 0) {
                valueDisplay.className = 'badge bg-secondary';
            } else {
                valueDisplay.className = 'badge bg-secondary';
            }
        }
        
        // Set data-value attribute for inline display
        slider.setAttribute('data-value', slider.value);
    }

    updateSortingInfo(weights) {
        const sortingInfo = document.getElementById('sorting-info');
        const sortingCriteria = document.getElementById('sorting-criteria');
        
        if (!sortingInfo || !sortingCriteria) return;
        
        const activeCriteria = [];
        Object.entries(weights).forEach(([key, value]) => {
            if (value !== 0) {
                const label = this.getCriteriaLabel(key);
                const direction = value > 0 ? 'Høy → Lav' : 'Lav → Høy';
                activeCriteria.push(`${label}: ${direction}`);
            }
        });
        
        if (activeCriteria.length > 0) {
            sortingCriteria.textContent = activeCriteria.join(', ');
            sortingInfo.style.display = 'block';
        } else {
            sortingInfo.style.display = 'none';
        }

        const activeCount = Object.values(weights).filter(v => v !== 0).length;
        const badge = document.getElementById('sorter-active-badge');
        if (badge) {
            badge.textContent = activeCount;
            badge.classList.toggle('d-none', activeCount === 0);
        }
    }

    getCriteriaLabel(key) {
        const labels = {
            helgetimer: 'Helgetimer',
            shift_cnt: 'Dagsverk',
            tidlig: 'Tidlig',
            natt: 'Natt',
            ettermiddag: 'Ettermiddag',
            before_6: 'Før 6:00',
            tidlig_6_8: 'Tidlig 6-8',
            tidlig_8_12: 'Tidlig 8-12',
            longest_off_streak: 'Lengste fri',
            longest_work_streak: 'Lengste rekke',
            avg_shift_hours: 'Snitt timer'
        };
        return labels[key] || key;
    }

    saveSortingSettings() {
        try {
            const settings = {
                helgetimer: document.getElementById('helgetimer-slider').value,
                shift_cnt: document.getElementById('shift-cnt-slider').value,
                tidlig: document.getElementById('tidlig-slider').value,
                natt: document.getElementById('natt-slider').value,
                ettermiddag: document.getElementById('ettermiddag-slider').value,
                before_6: document.getElementById('before-6-slider').value,
                tidlig_6_8: document.getElementById('tidlig-6-8-slider').value,
                tidlig_8_12: document.getElementById('tidlig-8-12-slider').value,
                longest_off_streak: document.getElementById('longest-off-slider').value,
                longest_work_streak: document.getElementById('longest-streak-slider').value,
                avg_shift_hours: document.getElementById('avg-hours-slider').value
            };
            localStorage.setItem('turnuslisteSortingSettings', JSON.stringify(settings));
            console.log('Sorting settings saved:', settings);
        } catch (error) {
            console.error('Error saving sorting settings:', error);
        }
    }

    loadSortingSettings() {
        try {
            const saved = localStorage.getItem('turnuslisteSortingSettings');
            if (saved) {
                const settings = JSON.parse(saved);
                console.log('Loading sorting settings:', settings);
                return settings;
            }
        } catch (error) {
            console.warn('Error loading sorting settings:', error);
        }
        return null;
    }

    applySavedSettings() {
        const settings = this.loadSortingSettings();
        if (!settings) return false;

        let anySettingsApplied = false;
        
        // Apply to desktop sliders
        Object.entries(settings).forEach(([key, value]) => {
            const sliderId = key === 'shift_cnt' ? 'shift-cnt-slider' :
                           key === 'before_6' ? 'before-6-slider' :
                           key === 'tidlig_6_8' ? 'tidlig-6-8-slider' :
                           key === 'tidlig_8_12' ? 'tidlig-8-12-slider' :
                           key === 'longest_off_streak' ? 'longest-off-slider' :
                           key === 'longest_work_streak' ? 'longest-streak-slider' :
                           key === 'avg_shift_hours' ? 'avg-hours-slider' :
                           `${key}-slider`;
            
            const slider = document.getElementById(sliderId);
            const mobileSlider = document.getElementById(sliderId + '-mobile');
            
            if (slider && value !== undefined && value !== '0') {
                slider.value = value;
                this.updateSliderValue(slider);
                anySettingsApplied = true;
            }
            
            if (mobileSlider && value !== undefined && value !== '0') {
                mobileSlider.value = value;
                this.updateSliderValue(mobileSlider);
            }
        });

        return anySettingsApplied;
    }

    setupEventListeners() {
        // Add event listeners to sliders (both desktop and mobile filters)
        const sliders = document.querySelectorAll('input[type="range"]');
        sliders.forEach(slider => {
            // Set initial value display
            this.updateSliderValue(slider);
            
            slider.addEventListener('input', () => {
                this.updateSliderValue(slider);
                
                // Sync mobile and desktop sliders
                const sliderId = slider.id;
                if (sliderId.includes('-mobile')) {
                    const desktopId = sliderId.replace('-mobile', '');
                    const desktopSlider = document.getElementById(desktopId);
                    if (desktopSlider) {
                        desktopSlider.value = slider.value;
                        this.updateSliderValue(desktopSlider);
                    }
                } else {
                    const mobileId = sliderId + '-mobile';
                    const mobileSlider = document.getElementById(mobileId);
                    if (mobileSlider) {
                        mobileSlider.value = slider.value;
                        this.updateSliderValue(mobileSlider);
                    }
                }
                
                this.sortTurnuser();
                this.saveSortingSettings(); // Save settings after each change
            });
        });
        
        // Add event listener to reset buttons (both desktop and mobile)
        const resetButtons = document.querySelectorAll('#reset-sorting, #reset-sorting-mobile');
        resetButtons.forEach(button => {
            button.addEventListener('click', () => this.resetOrder());
        });

        // Make hideSortingInfo available globally for backward compatibility
        window.hideSortingInfo = () => {
            this.resetOrder();
        };

        // Fix aria-hidden warning: blur any focused element inside the modal before it hides
        const modal = document.getElementById('mobileSorterModal');
        if (modal) {
            modal.addEventListener('hide.bs.modal', () => {
                const focused = modal.querySelector(':focus');
                if (focused) focused.blur();
            });
        }
    }
}
