/**
 * Shift Timeline Modal Module
 * Displays a modal with the strekliste PNG for a dagsverk.
 *
 * The image is shown at a fixed, readable size inside a scroll box instead of
 * being shrunk to fit: the PNG is a ~8:1 strip covering 24 hours, so fitting
 * it to a phone's width left the text unreadable. Scrolling and pinch-zoom are
 * the browser's own; the only custom input handling is mouse drag-to-scroll.
 */

// Where the hour axis sits in a strekliste PNG, in natural pixels. Follows from
// compute_page_geometry() in strekliste_generator.py at PDF_ZOOM 4: the crop
// starts 22 pt into the page and hour 0 is printed at 103.5 pt, so hour 0 is
// 326 px in; the crop ends 4 pt past the hour-24 gridline, 16 px from the
// right. Holds for both the 19.5 and the 30 pt/hour PDF editions; only used to
// pick the opening scroll position.
const HOUR_0_PX = 326;
const HOUR_24_FROM_RIGHT_PX = 16;

// Open this many hours before the duty starts, so the start is not flush left
const LEAD_HOURS = 0.5;

const SCALES = [0.6, 0.8, 1, 1.3];
const DEFAULT_SCALE_INDEX = 1;

export class ShiftTimelineModal {
    constructor() {
        this.modal = null;
        this.modalImage = null;
        this.modalTitle = null;
        this.modalSpinner = null;
        this.modalError = null;
        this.imageWrapper = null;
        this.scroller = null;

        this.scaleIndex = DEFAULT_SCALE_INDEX;
        this.startHour = null;

        this.init();
    }

    /**
     * Extract numeric prefix from shift name for image lookup
     * Examples: "123HLD" -> "123", "456SKNO" -> "456", "789" -> "789"
     */
    extractNumericPrefix(shiftNr) {
        const match = shiftNr.match(/^(\d+)/);
        return match ? match[1] : shiftNr;
    }

    /**
     * Read the start time from the cell's time text ("05:33 - 14:41").
     * Returns fractional hours, or null when the cell has no time.
     */
    parseStartHour(timeText) {
        const match = (timeText || '').match(/(\d{1,2}):(\d{2})/);
        return match ? parseInt(match[1], 10) + parseInt(match[2], 10) / 60 : null;
    }

    init() {
        // Get modal elements
        this.modal = document.getElementById('shiftTimelineModal');
        if (!this.modal) return;

        this.modalImage = document.getElementById('shiftTimelineImage');
        this.modalTitle = document.getElementById('shiftTimelineTitle');
        this.modalSpinner = document.getElementById('shiftTimelineSpinner');
        this.modalError = document.getElementById('shiftTimelineError');
        this.modalErrorText = document.getElementById('shiftTimelineErrorText');
        this.modalErrorIcon = document.getElementById('shiftTimelineErrorIcon');
        this.imageWrapper = document.getElementById('shiftTimelineWrapper');
        this.scroller = document.getElementById('shiftTimelineScroller');

        // Set up click handlers on shift names
        this.setupClickHandlers();

        // Set up zoom buttons and mouse drag
        this.setupZoomButtons();
        this.setupDragScroll();

        // Next duty opens at the default size again
        this.modal.addEventListener('hidden.bs.modal', () => {
            this.scaleIndex = DEFAULT_SCALE_INDEX;
        });
    }

    setupClickHandlers() {
        // Event delegation: one listener on body catches clicks on any .dagsverk-link,
        // including elements inserted lazily after page load.
        document.body.addEventListener('click', (e) => {
            const element = e.target.closest('.dagsverk-link');
            if (!element) return;

            const shiftNr = element.dataset.shiftNr;
            const container = element.closest('.printable');
            const turnusSetId = container?.dataset.currentTurnusSetId;

            if (!turnusSetId || !shiftNr || !shiftNr.trim()) return;

            const trimmedShiftNr = shiftNr.trim();
            if (trimmedShiftNr.startsWith('9') && trimmedShiftNr.length > 8) return;

            e.preventDefault();
            e.stopPropagation();

            const timeText = element.closest('td')?.querySelector('.time-text')?.textContent;
            this.show(turnusSetId, trimmedShiftNr, this.parseStartHour(timeText));
        });

        // Apply visual hint to elements already in the DOM (non-lazy pages like /favorites)
        this.applyTriggerMarkup(document);
    }

    // Mark valid .dagsverk-link elements within a root with cursor + tooltip.
    // Called once for the document on init, and again by LazyTables for each
    // newly inserted table so lazy-loaded cells also get the visual hint.
    applyTriggerMarkup(root) {
        root.querySelectorAll('.dagsverk-link').forEach(element => {
            const shiftNr = element.dataset.shiftNr;
            const container = element.closest('.printable');
            const turnusSetId = container?.dataset.currentTurnusSetId;

            if (!turnusSetId || !shiftNr || !shiftNr.trim()) return;

            const trimmedShiftNr = shiftNr.trim();
            if (trimmedShiftNr.startsWith('9') && trimmedShiftNr.length > 8) return;

            element.classList.add('shift-timeline-trigger');
            element.title = 'Klikk for strekliste';
        });
    }

    async show(turnusSetId, shiftNr, startHour = null) {
        if (!this.modal) return;

        this.startHour = startHour;

        // Strip suffixes for image lookup
        const lookupShiftNr = this.extractNumericPrefix(shiftNr);

        // Show modal
        const bsModal = new bootstrap.Modal(this.modal);
        bsModal.show();

        // Set title (show original name)
        if (this.modalTitle) {
            this.modalTitle.textContent = `Turnus ${shiftNr}`;
        }

        // Show loading state
        this.setLoading(true);

        try {
            const response = await fetch(`/api/shift-image/${turnusSetId}/${lookupShiftNr}`);

            if (response.ok) {
                const blob = await response.blob();
                const imageUrl = URL.createObjectURL(blob);

                if (this.modalImage) {
                    this.modalImage.src = imageUrl;
                    this.modalImage.onload = () => {
                        this.setLoading(false);
                        this.showImage();
                    };
                    this.modalImage.onerror = () => {
                        this.setLoading(false);
                        this.showError('Kunne ikke vise bildet');
                    };
                }
            } else if (response.status === 404) {
                this.setLoading(false);
                this.showNotFound(shiftNr);
            } else {
                const data = await response.json();
                this.setLoading(false);
                this.showError(data.message || 'Kunne ikke laste tidslinje');
            }
        } catch (error) {
            this.setLoading(false);
            this.showError('Nettverksfeil - kunne ikke laste tidslinje');
        }
    }

    setLoading(loading) {
        if (this.modalSpinner) {
            this.modalSpinner.style.display = loading ? 'block' : 'none';
        }
        if (this.imageWrapper) {
            this.imageWrapper.style.display = 'none';
        }
        if (this.modalError) {
            this.modalError.style.display = 'none';
        }
    }

    showImage() {
        if (this.imageWrapper) {
            this.imageWrapper.style.display = 'block';
        }
        if (this.modalError) {
            this.modalError.style.display = 'none';
        }
        this.applyScale();

        // A cached image can load before Bootstrap has laid out the modal
        // (it waits for the backdrop fade); scrolling then would be ignored
        if (this.scroller && this.scroller.clientWidth === 0) {
            this.modal.addEventListener('shown.bs.modal', () => this.scrollToStart(), { once: true });
        } else {
            this.scrollToStart();
        }
    }

    showError(message) {
        if (this.modalError) {
            this.modalError.className = 'alert alert-warning m-3';
            if (this.modalErrorIcon) {
                this.modalErrorIcon.className = 'bi bi-exclamation-triangle me-2';
            }
            if (this.modalErrorText) {
                this.modalErrorText.textContent = message;
            }
            this.modalError.style.display = 'block';
        }
        if (this.imageWrapper) {
            this.imageWrapper.style.display = 'none';
        }
    }

    showNotFound(shiftNr) {
        if (this.modalError) {
            this.modalError.className = 'alert alert-info m-3';
            if (this.modalErrorIcon) {
                this.modalErrorIcon.className = 'bi bi-info-circle me-2';
            }
            if (this.modalErrorText) {
                this.modalErrorText.textContent = `Ingen strekliste er tilgjengelig for turnus ${shiftNr}.`;
            }
            this.modalError.style.display = 'block';
        }
        if (this.imageWrapper) {
            this.imageWrapper.style.display = 'none';
        }
    }

    hide() {
        if (this.modal) {
            const bsModal = bootstrap.Modal.getInstance(this.modal);
            if (bsModal) {
                bsModal.hide();
            }
        }
    }

    // Size and scroll

    applyScale() {
        if (!this.modalImage || !this.modalImage.naturalWidth) return;
        const scale = SCALES[this.scaleIndex];
        this.modalImage.style.width = `${this.modalImage.naturalWidth * scale}px`;
        this.updateZoomButtons();
    }

    // Scroll so the duty's start is just inside the left edge. Without a start
    // time the box stays at the left, which shows the duty number columns.
    scrollToStart() {
        if (!this.scroller || !this.modalImage) return;
        if (this.startHour === null) {
            this.scroller.scrollLeft = 0;
            return;
        }
        const naturalWidth = this.modalImage.naturalWidth;
        const pxPerHour = (naturalWidth - HOUR_0_PX - HOUR_24_FROM_RIGHT_PX) / 24;
        const hour = Math.max(0, this.startHour - LEAD_HOURS);
        const scale = this.modalImage.offsetWidth / naturalWidth;
        this.scroller.scrollLeft = (HOUR_0_PX + hour * pxPerHour) * scale;
    }

    setScale(index) {
        if (!this.scroller || !this.modalImage) return;
        const clamped = Math.min(SCALES.length - 1, Math.max(0, index));
        if (clamped === this.scaleIndex) return;

        // Keep the part of the duty in the middle of the box where it is
        const oldWidth = this.modalImage.offsetWidth;
        const centre = (this.scroller.scrollLeft + this.scroller.clientWidth / 2) / oldWidth;

        this.scaleIndex = clamped;
        this.applyScale();
        this.scroller.scrollLeft = centre * this.modalImage.offsetWidth - this.scroller.clientWidth / 2;
    }

    setupZoomButtons() {
        const zoomInBtn = document.getElementById('shiftTimelineZoomIn');
        const zoomOutBtn = document.getElementById('shiftTimelineZoomOut');
        const zoomResetBtn = document.getElementById('shiftTimelineZoomReset');

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => this.setScale(this.scaleIndex + 1));
        }
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => this.setScale(this.scaleIndex - 1));
        }
        if (zoomResetBtn) {
            zoomResetBtn.addEventListener('click', () => {
                this.scaleIndex = DEFAULT_SCALE_INDEX;
                this.applyScale();
                this.scrollToStart();
            });
        }
    }

    // Mouse only: touch and trackpads already scroll the box natively
    setupDragScroll() {
        if (!this.scroller) return;

        let startX = 0;
        let startY = 0;
        let startLeft = 0;
        let startTop = 0;

        this.scroller.addEventListener('pointerdown', (e) => {
            if (e.pointerType !== 'mouse' || e.button !== 0) return;
            // A press on the scroll box's own scrollbar targets the box, not the image
            if (e.target !== this.modalImage) return;
            startX = e.clientX;
            startY = e.clientY;
            startLeft = this.scroller.scrollLeft;
            startTop = this.scroller.scrollTop;
            this.scroller.setPointerCapture(e.pointerId);
            this.scroller.classList.add('dragging');
            e.preventDefault();
        });

        this.scroller.addEventListener('pointermove', (e) => {
            if (!this.scroller.classList.contains('dragging')) return;
            this.scroller.scrollLeft = startLeft - (e.clientX - startX);
            this.scroller.scrollTop = startTop - (e.clientY - startY);
        });

        const endDrag = () => this.scroller.classList.remove('dragging');
        this.scroller.addEventListener('pointerup', endDrag);
        this.scroller.addEventListener('pointercancel', endDrag);
    }

    updateZoomButtons() {
        const zoomInBtn = document.getElementById('shiftTimelineZoomIn');
        const zoomOutBtn = document.getElementById('shiftTimelineZoomOut');
        const zoomLevel = document.getElementById('shiftTimelineZoomLevel');

        if (zoomInBtn) {
            zoomInBtn.disabled = this.scaleIndex >= SCALES.length - 1;
        }
        if (zoomOutBtn) {
            zoomOutBtn.disabled = this.scaleIndex <= 0;
        }
        if (zoomLevel) {
            zoomLevel.textContent = `${Math.round(SCALES[this.scaleIndex] * 100)}%`;
        }
    }
}

export default ShiftTimelineModal;
