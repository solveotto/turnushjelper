/**
 * Shift Timeline Modal Module
 * Displays a modal with shift timeline image from static files
 * Includes smooth pan and zoom functionality
 */

export class ShiftTimelineModal {
    constructor() {
        this.modal = null;
        this.modalImage = null;
        this.modalTitle = null;
        this.modalSpinner = null;
        this.modalError = null;
        this.imageContainer = null;

        // Zoom/pan state
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.lastTranslateX = 0;
        this.lastTranslateY = 0;

        // Zoom settings
        this.minScale = 1;
        this.maxScale = 5;
        this.zoomStep = 0.25;

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
        this.imageContainer = document.getElementById('shiftTimelineContainer');
        this.imageWrapper = document.getElementById('shiftTimelineWrapper');

        // Set up click handlers on shift names
        this.setupClickHandlers();

        // Set up zoom/pan handlers
        this.setupZoomPanHandlers();

        // Reset zoom when modal closes
        this.modal.addEventListener('hidden.bs.modal', () => this.resetZoom());

        // Set up resize bar
        this.setupResizeBar();
    }

    setupResizeBar() {
        const resizeBar = document.getElementById('shiftTimelineResizeBar');
        if (!resizeBar || !this.imageWrapper) return;

        let startY, startHeight;

        const onMouseMove = (e) => {
            const newHeight = startHeight + (e.clientY - startY);
            const clamped = Math.max(150, Math.min(window.innerHeight * 0.85, newHeight));
            this.imageWrapper.style.height = clamped + 'px';
        };

        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };

        resizeBar.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startY = e.clientY;
            startHeight = this.imageWrapper.offsetHeight;
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
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
            this.show(turnusSetId, trimmedShiftNr);
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

    async show(turnusSetId, shiftNr) {
        if (!this.modal) return;

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
                        this.sizeContainerToImage();
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
        if (this.modalImage) {
            this.modalImage.style.display = 'none';
        }
        if (this.modalError) {
            this.modalError.style.display = 'none';
        }
    }

    sizeContainerToImage() {
        if (!this.modalImage || !this.imageWrapper) return;

        // Get the image's natural aspect ratio and the wrapper width
        const wrapperWidth = this.imageWrapper.clientWidth - 32; // minus padding
        const imgNaturalWidth = this.modalImage.naturalWidth;
        const imgNaturalHeight = this.modalImage.naturalHeight;

        // Calculate how tall the image will be when scaled to fit wrapper width
        const scaledHeight = (imgNaturalHeight / imgNaturalWidth) * wrapperWidth;

        // Set wrapper height to image height + small padding, capped at 85vh
        const maxHeight = window.innerHeight * 0.85;
        const targetHeight = Math.min(scaledHeight + 32, maxHeight);

        this.imageWrapper.style.height = targetHeight + 'px';
    }

    showImage() {
        if (this.modalImage) {
            this.modalImage.style.display = 'block';
        }
        if (this.modalError) {
            this.modalError.style.display = 'none';
        }
        this.resetZoom();
        this.updateZoomButtons();
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
        if (this.modalImage) {
            this.modalImage.style.display = 'none';
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
        if (this.modalImage) {
            this.modalImage.style.display = 'none';
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

    // Zoom and pan functionality
    setupZoomPanHandlers() {
        if (!this.imageContainer || !this.modalImage) return;

        // Mouse wheel zoom
        this.imageContainer.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -this.zoomStep : this.zoomStep;
            this.zoom(delta, e.clientX, e.clientY);
        }, { passive: false });

        // Mouse drag for panning
        this.imageContainer.addEventListener('mousedown', (e) => {
            if (this.scale > 1) {
                this.isDragging = true;
                this.dragStartX = e.clientX;
                this.dragStartY = e.clientY;
                this.lastTranslateX = this.translateX;
                this.lastTranslateY = this.translateY;
                this.imageContainer.style.cursor = 'grabbing';
                e.preventDefault();
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                const dx = e.clientX - this.dragStartX;
                const dy = e.clientY - this.dragStartY;
                this.translateX = this.lastTranslateX + dx;
                this.translateY = this.lastTranslateY + dy;
                this.constrainPan();
                this.applyTransform();
            }
        });

        document.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                if (this.imageContainer) {
                    this.imageContainer.style.cursor = this.scale > 1 ? 'grab' : 'default';
                }
            }
        });

        // Touch support for mobile
        let lastTouchDistance = 0;
        let lastTouchCenter = { x: 0, y: 0 };

        this.imageContainer.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                lastTouchDistance = this.getTouchDistance(e.touches);
                lastTouchCenter = this.getTouchCenter(e.touches);
            } else if (e.touches.length === 1 && this.scale > 1) {
                this.isDragging = true;
                this.dragStartX = e.touches[0].clientX;
                this.dragStartY = e.touches[0].clientY;
                this.lastTranslateX = this.translateX;
                this.lastTranslateY = this.translateY;
            }
        }, { passive: true });

        this.imageContainer.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const currentDistance = this.getTouchDistance(e.touches);
                const currentCenter = this.getTouchCenter(e.touches);
                const scaleDelta = (currentDistance - lastTouchDistance) * 0.01;
                this.zoom(scaleDelta, currentCenter.x, currentCenter.y);
                lastTouchDistance = currentDistance;
                lastTouchCenter = currentCenter;
            } else if (e.touches.length === 1 && this.isDragging) {
                const dx = e.touches[0].clientX - this.dragStartX;
                const dy = e.touches[0].clientY - this.dragStartY;
                this.translateX = this.lastTranslateX + dx;
                this.translateY = this.lastTranslateY + dy;
                this.constrainPan();
                this.applyTransform();
            }
        }, { passive: false });

        this.imageContainer.addEventListener('touchend', () => {
            this.isDragging = false;
            lastTouchDistance = 0;
        });

        // Zoom buttons
        const zoomInBtn = document.getElementById('shiftTimelineZoomIn');
        const zoomOutBtn = document.getElementById('shiftTimelineZoomOut');
        const zoomResetBtn = document.getElementById('shiftTimelineZoomReset');

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => this.zoomIn());
        }
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => this.zoomOut());
        }
        if (zoomResetBtn) {
            zoomResetBtn.addEventListener('click', () => this.resetZoom());
        }
    }

    getTouchDistance(touches) {
        const dx = touches[0].clientX - touches[1].clientX;
        const dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    getTouchCenter(touches) {
        return {
            x: (touches[0].clientX + touches[1].clientX) / 2,
            y: (touches[0].clientY + touches[1].clientY) / 2
        };
    }

    zoom(delta, centerX, centerY) {
        const oldScale = this.scale;
        this.scale = Math.min(this.maxScale, Math.max(this.minScale, this.scale + delta));

        if (this.scale !== oldScale && this.imageWrapper) {
            // Zoom toward cursor/touch point
            const rect = this.imageWrapper.getBoundingClientRect();
            const x = centerX - rect.left - rect.width / 2;
            const y = centerY - rect.top - rect.height / 2;
            const scaleDiff = this.scale / oldScale;

            this.translateX = x - (x - this.translateX) * scaleDiff;
            this.translateY = y - (y - this.translateY) * scaleDiff;

            this.constrainPan();
            this.applyTransform();
            this.updateZoomButtons();
            this.updateCursor();
        }
    }

    zoomIn() {
        if (this.imageWrapper) {
            const rect = this.imageWrapper.getBoundingClientRect();
            this.zoom(this.zoomStep, rect.left + rect.width / 2, rect.top + rect.height / 2);
        }
    }

    zoomOut() {
        if (this.imageWrapper) {
            const rect = this.imageWrapper.getBoundingClientRect();
            this.zoom(-this.zoomStep, rect.left + rect.width / 2, rect.top + rect.height / 2);
        }
    }

    resetZoom() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.applyTransform();
        this.updateZoomButtons();
        this.updateCursor();
        // Reset wrapper height for next image
        if (this.imageWrapper) {
            this.imageWrapper.style.height = '';
        }
    }

    constrainPan() {
        if (!this.modalImage || !this.imageWrapper) return;

        const wrapperRect = this.imageWrapper.getBoundingClientRect();
        const imgWidth = this.modalImage.offsetWidth * this.scale;
        const imgHeight = this.modalImage.offsetHeight * this.scale;

        const maxX = Math.max(0, (imgWidth - wrapperRect.width) / 2);
        const maxY = Math.max(0, (imgHeight - wrapperRect.height) / 2);

        this.translateX = Math.min(maxX, Math.max(-maxX, this.translateX));
        this.translateY = Math.min(maxY, Math.max(-maxY, this.translateY));
    }

    applyTransform() {
        if (this.modalImage) {
            this.modalImage.style.transform = `translate(${this.translateX}px, ${this.translateY}px) scale(${this.scale})`;
        }
    }

    updateCursor() {
        if (this.imageContainer) {
            this.imageContainer.style.cursor = this.scale > 1 ? 'grab' : 'default';
        }
    }

    updateZoomButtons() {
        const zoomInBtn = document.getElementById('shiftTimelineZoomIn');
        const zoomOutBtn = document.getElementById('shiftTimelineZoomOut');
        const zoomLevel = document.getElementById('shiftTimelineZoomLevel');

        if (zoomInBtn) {
            zoomInBtn.disabled = this.scale >= this.maxScale;
        }
        if (zoomOutBtn) {
            zoomOutBtn.disabled = this.scale <= this.minScale;
        }
        if (zoomLevel) {
            zoomLevel.textContent = `${Math.round(this.scale * 100)}%`;
        }
    }
}

export default ShiftTimelineModal;
