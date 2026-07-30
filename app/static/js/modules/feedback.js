/**
 * Feedback / Support Modal Module
 * Sends a category + message to /feedback/send and shows a persistent
 * success/error result inside the modal.
 */

export class FeedbackModal {
    constructor() {
        this.modal = null;
        this.form = null;
        this.pageUrlInput = null;
        this.errorBox = null;
        this.successBox = null;
        this.submitBtn = null;

        this.init();
    }

    init() {
        this.modal = document.getElementById('feedbackModal');
        if (!this.modal) return;

        this.form = document.getElementById('feedbackForm');
        this.pageUrlInput = document.getElementById('feedbackPageUrl');
        this.errorBox = document.getElementById('feedbackError');
        this.successBox = document.getElementById('feedbackSuccess');
        this.submitBtn = document.getElementById('feedbackSubmitBtn');

        this.modal.addEventListener('show.bs.modal', () => this.resetForm());
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
    }

    resetForm() {
        this.pageUrlInput.value = window.location.href;
        this.errorBox.style.display = 'none';
        this.successBox.style.display = 'none';
        this.form.style.display = '';
        this.submitBtn.style.display = '';
        this.submitBtn.disabled = false;
    }

    async handleSubmit(event) {
        event.preventDefault();
        this.errorBox.style.display = 'none';
        this.submitBtn.disabled = true;

        try {
            const response = await apiFetch('/feedback/send', {
                method: 'POST',
                body: new FormData(this.form),
            });
            const data = await response.json();

            if (data.success) {
                this.form.style.display = 'none';
                this.submitBtn.style.display = 'none';
                this.successBox.style.display = '';
            } else {
                this.showError(data.error || 'Kunne ikke sende tilbakemelding.');
            }
        } catch (err) {
            this.showError('Kunne ikke sende tilbakemelding. Sjekk internettforbindelsen din.');
        } finally {
            this.submitBtn.disabled = false;
        }
    }

    showError(message) {
        this.errorBox.textContent = message;
        this.errorBox.style.display = '';
    }
}
