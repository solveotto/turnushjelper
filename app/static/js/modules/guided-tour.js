// Guided Tour Module
// Manages Driver.js-based guided tours for onboarding new users

export class GuidedTour {
    constructor() {
        this.driver = null;
        this.init();
    }

    init() {
        // Only run on pages that have tour data
        const pageLayout = document.querySelector('.page-layout');
        if (!pageLayout) return;

        this.tourSeen = pageLayout.dataset.tourSeen;
        this.setupHelpButton();
        this.detectAndStartTour();
    }

    setupHelpButton() {
        const helpBtn = document.getElementById('start-tour-btn');
        if (helpBtn) {
            helpBtn.addEventListener('click', () => this.startTour());
        }
    }

    detectAndStartTour() {
        // Auto-start tour if user hasn't seen it (1s delay for page to settle)
        if (this.tourSeen === '0') {
            setTimeout(() => this.startTour(), 1000);
        }
    }

    async startTour() {
        // Determine which page we're on and load the correct steps
        const steps = await this.getStepsForCurrentPage();
        if (!steps || steps.length === 0) return;

        // Create a new Driver instance each time (clean state)
        // driver.js is loaded via CDN as a global
        if (typeof window.driver === 'undefined') {
            console.warn('Driver.js not loaded');
            return;
        }

        this.driver = window.driver.js.driver({
            showProgress: true,
            animate: true,
            overlayColor: 'rgba(30, 58, 138, 0.6)',
            stagePadding: 8,
            stageRadius: 8,
            allowClose: true,
            popoverClass: 'guided-tour-popover',
            progressText: '{{current}} av {{total}}',
            nextBtnText: 'Neste →',
            prevBtnText: '← Forrige',
            doneBtnText: 'Ferdig ✓',
            steps: steps,
            onDestroyStarted: () => {
                // Mark tour as seen when user completes or closes the tour
                if (this.tourSeen === '0') {
                    this.markTourSeen();
                }
                this.driver.destroy();
            },
        });

        this.driver.drive();
    }

    async getStepsForCurrentPage() {
        // Detect current page and load appropriate tour steps
        if (document.querySelector('.page-layout')) {
            // We're on the turnusliste page (it has .page-layout)
            const { getTurnuslisteTourSteps } = await import('./tour-definitions/turnusliste-tour.js');
            return getTurnuslisteTourSteps();
        }
        return null;
    }

    async markTourSeen() {
        try {
            const response = await fetch('/api/mark-tour-seen', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tour_name: 'turnusliste' }),
            });
            const data = await response.json();
            if (data.status === 'success') {
                // Update the data attribute so re-triggering doesn't re-POST
                const pageLayout = document.querySelector('.page-layout');
                if (pageLayout) {
                    pageLayout.dataset.tourSeen = '1';
                    this.tourSeen = '1';
                }
            }
        } catch (err) {
            console.warn('Could not mark tour as seen:', err);
        }
    }
}
