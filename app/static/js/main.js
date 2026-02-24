// Main JavaScript entry point
// Coordinates all modules and handles initialization

import { ShiftSelection } from './modules/shift-selection.js';
import { ShiftColors } from './modules/shift-colors.js';
import { PostNightMarker } from './modules/post-night-marker.js';
import { SortingSystem } from './modules/sorting-system.js';
import { Favorites } from './modules/favorites.js';
import { PrintUtils } from './modules/print-utils.js';
import { ShiftTimelineModal } from './modules/shift-timeline.js';
import { GuidedTour } from './modules/guided-tour.js';
import { LazyTables } from './modules/lazy-tables.js';

// NOT USED
// import { Utils, ScrollPosition } from './modules/utils.js';
// import { ColorAdjustment } from './modules/color-adjustment.js';

class App {
    constructor() {
        this.modules = {};
        this.init();
    }

    init() {
        // Initialize modules based on page context
        this.initializeModules();
    }

    initializeModules() {
        // Always initialize these modules
        this.modules.favorites = new Favorites();
        // this.modules.scrollPosition = new ScrollPosition(); // Disabled - Utils not imported

        // Initialize shift colors if we have table cells OR lazy tables pending render
        const hasLazyTables = !!document.querySelector('template[data-lazy-table]');
        if (hasLazyTables || document.querySelector('td[id="cell"]')) {
            this.modules.shiftColors = new ShiftColors();
            // Mark post-night recovery cells (must run after shift colors)
            this.modules.postNightMarker = new PostNightMarker();
        }

        // Initialize shift timeline modal before LazyTables so it can be passed in
        if (document.querySelector('#shiftTimelineModal')) {
            this.modules.shiftTimeline = new ShiftTimelineModal();
        }

        // Initialize lazy table loader (defers heavy table DOM until scroll-into-view)
        if (hasLazyTables) {
            this.modules.lazyTables = new LazyTables(
                this.modules.shiftColors,
                this.modules.postNightMarker,
                this.modules.shiftTimeline
            );
        }

        // Initialize shift selection if we have clickable rows
        if (document.querySelector('.clickable-row')) {
            this.modules.shiftSelection = new ShiftSelection();
        }

        // Initialize color adjustment if we're on the turnusliste page (user customization UI)
        // Note: ColorAdjustment module is commented out - uncomment import above to re-enable
        // if (document.querySelector('#apply-colors')) {
        //     this.modules.colorAdjustment = new ColorAdjustment();
        // }

        // Initialize sorting if we're on the turnusliste page
        if (document.querySelector('#helgetimer-slider')) {
            this.modules.sorting = new SortingSystem();
        }

        // Initialize guided tour (handles help button on all pages,
        // auto-starts tour only on pages with data-tour-page)
        this.modules.guidedTour = new GuidedTour();
    }

    getModule(name) {
        return this.modules[name];
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});

// Export for potential external access
export default App;
