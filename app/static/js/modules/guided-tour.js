// Guided Tour Module
// Manages Driver.js-based guided tours for onboarding new users
// and a separate help guide accessible from the dropdown menu.
// Page detection is data-driven via [data-tour-page] attributes.

export class GuidedTour {
    constructor() {
        this.driver = null;
        this.init();
    }

    async init() {
        // Help menu: show the "Hjelp" link if help steps exist for this page
        const helpSteps = await this.getHelpStepsForCurrentPage();
        if (helpSteps && helpSteps.length > 0) {
            this.showHelpMenuItem();
            this.setupHelpButton();
        }

        // Onboarding tour: auto-start if user hasn't seen it (global flag)
        const tourSeenEl = document.querySelector('[data-tour-seen]');
        if (tourSeenEl) {
            this.tourSeen = tourSeenEl.dataset.tourSeen;
            if (this.tourSeen === '0') {
                const tourSteps = await this.getStepsForCurrentPage();
                if (tourSteps && tourSteps.length > 0) {
                    setTimeout(() => this.startTour(), 1000);
                }
            }
        }
    }

    showHelpMenuItem() {
        const desktopBtn = document.getElementById('help-icon-btn');
        if (desktopBtn) desktopBtn.style.display = '';

        const mobileItem = document.getElementById('help-icon-btn-mobile');
        if (mobileItem) mobileItem.style.display = '';
    }

    setupHelpButton() {
        const handler = (e) => {
            e.preventDefault();
            this.startHelp();
        };

        const desktopBtn = document.getElementById('help-icon-btn');
        if (desktopBtn) desktopBtn.addEventListener('click', handler);

        const mobileBtn = document.getElementById('help-icon-btn-mobile');
        if (mobileBtn) mobileBtn.addEventListener('click', handler);
    }

    async startHelp() {
        const steps = await this.getHelpStepsForCurrentPage();
        if (!steps || steps.length === 0) return;

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
        });

        this.driver.drive();
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
        const el = document.querySelector('[data-tour-page]');
        if (!el) return null;
        const page = el.dataset.tourPage;
        try {
            const mod = await import(`./tour-definitions/${page}-tour.js`);
            return mod.default?.() || null;
        } catch {
            return null;
        }
    }

    async getHelpStepsForCurrentPage() {
        const el = document.querySelector('[data-tour-page]');
        if (!el) return null;
        const page = el.dataset.tourPage;
        try {
            const mod = await import(`./tour-definitions/${page}-help.js`);
            return mod.default?.() || null;
        } catch {
            return null;
        }
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
                const tourSeenEl = document.querySelector('[data-tour-seen]');
                if (tourSeenEl) {
                    tourSeenEl.dataset.tourSeen = '1';
                    this.tourSeen = '1';
                }
            }
        } catch (err) {
            console.warn('Could not mark tour as seen:', err);
        }
    }
}
