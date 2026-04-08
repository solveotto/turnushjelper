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
        // Show help button if this page has a tour
        const pageSteps = await this.getPageSteps();
        if (pageSteps?.length > 0) {
            this.showHelpMenuItem();
            this.setupHelpButton();
        }

        const welcomeSeen = document.body.dataset.welcomeSeen;

        const pageEl = document.querySelector('[data-tour-page]');
        this.tourSeenEl = pageEl?.hasAttribute('data-tour-seen')
            ? pageEl
            : document.querySelector('[data-tour-seen]');
        this.pageSeen = this.tourSeenEl?.dataset.tourSeen;

        if (welcomeSeen === '0') {
            setTimeout(() => this.startWelcomeThenPage(), 1000);
        } else if (this.pageSeen === '0') {
            setTimeout(() => this.startPageTour(), 1000);
        }
    }

    _startDriverWith(steps, onDestroy = null) {
        if (typeof window.driver === 'undefined') {
            console.warn('Driver.js not loaded');
            return;
        }

        this._blockKeyScroll = (e) => {
            const scrollKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
                                ' ', 'PageUp', 'PageDown', 'Home', 'End'];
            if (scrollKeys.includes(e.key)) e.preventDefault();
        };
        this._blockTouchScroll = (e) => e.preventDefault();
        this._blockWheelScroll = (e) => e.preventDefault();

        const config = {
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
            steps,
            onDestroyStarted: () => {
                this.driver.destroy();
                this._unlockScroll();
                if (onDestroy) onDestroy();
            },
        };

        document.body.style.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';
        document.addEventListener('keydown', this._blockKeyScroll);
        document.addEventListener('touchmove', this._blockTouchScroll, { passive: false });
        document.addEventListener('wheel', this._blockWheelScroll, { passive: false });

        this.driver = window.driver.js.driver(config);
        this.driver.drive();
    }

    _unlockScroll() {
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        document.removeEventListener('keydown', this._blockKeyScroll);
        document.removeEventListener('touchmove', this._blockTouchScroll);
        document.removeEventListener('wheel', this._blockWheelScroll);
    }

    showHelpMenuItem() {
        const helpBtn = document.getElementById('help-icon-btn');
        if (helpBtn) helpBtn.style.display = '';
    }

    setupHelpButton() {
        const handler = (e) => {
            e.preventDefault();
            this.startHelp();
        };

        const helpBtn = document.getElementById('help-icon-btn');
        if (helpBtn) helpBtn.addEventListener('click', handler);
    }

    async startHelp() {
        const steps = await this.getPageSteps();
        if (!steps?.length) return;
        this._startDriverWith(steps);
    }

    async startWelcomeThenPage() {
        const welcomeSteps = await this.getWelcomeSteps();
        if (!welcomeSteps?.length) {
            // No welcome file — fall straight through to page tour
            await this.startPageTour();
            return;
        }

        this._startDriverWith(welcomeSteps, async () => {
            await this.markSeen('welcome');
            if (this.pageSeen === '0') {
                setTimeout(() => this.startPageTour(), 400);
            }
        });
    }

    async startPageTour() {
        const steps = await this.getPageSteps();
        if (!steps?.length) return;
        this._startDriverWith(steps, async () => {
            await this.markSeen(this.getPageName());
        });
    }

    async getWelcomeSteps() {
        try {
            const mod = await import('./tour-definitions/welcome-tour.js');
            return mod.default?.() || null;
        } catch {
            return null;
        }
    }

    async getPageSteps() {
        const page = this.getPageName();
        if (!page) return null;
        try {
            const mod = await import(`./tour-definitions/${page}-tour.js`);
            return mod.default?.() || null;
        } catch {
            return null;
        }
    }

    getPageName() {
        return document.querySelector('[data-tour-page]')?.dataset.tourPage || null;
    }

    async markSeen(name) {
        try {
            const response = await fetch('/api/mark-tour-seen', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tour_name: name }),
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (name === 'welcome') {
                    document.body.dataset.welcomeSeen = '1';
                } else if (this.tourSeenEl) {
                    this.tourSeenEl.dataset.tourSeen = '1';
                    this.pageSeen = '1';
                }
            }
        } catch (err) {
            console.warn('Could not mark tour as seen:', err);
        }
    }
}
