// Redusert Stilling Module
// A driver's plan for a reduced position on Min Tur: a percentage, and the
// shifts to give up. The page only ever changes from the server's response.

import { apiFetch } from './utils.js';

const ROUTE = '/mintur/redusert-stilling';
const SAVE_FAILED = 'Kunne ikke lagre. Last siden på nytt og prøv igjen.';

export class RedusertStilling {
    constructor(postNightMarker) {
        this.postNightMarker = postNightMarker;
        this.panel = document.getElementById('redusertPanel');
        this.container = this.panel.closest('.printable');
        this.turnusSetId = Number(this.container.dataset.currentTurnusSetId);
        this.prosentInput = document.getElementById('redusertProsent');
        this.velgButton = document.getElementById('redusertVelg');
        this.errorBox = document.getElementById('redusertFeil');

        this.selecting = false;
        this.removed = new Set(JSON.parse(this.panel.dataset.fjernet));
        this.savedProsent = this.prosentInput.value;
        // Not there for a tur without an H-dag.
        this.hDagBox = document.getElementById('redusertHdag');
        this.savedHdag = this.hDagBox?.checked;

        // One request at a time, so quick clicks can't overwrite each other.
        // wanted tracks what those clicks asked for until the answers are in.
        this.queue = Promise.resolve();
        this.waiting = 0;
        this.wanted = new Map();

        this.velgButton.addEventListener('click', () => this.toggleSelecting());
        this.prosentInput.addEventListener('change', () => this.saveProsent());
        this.hDagBox?.addEventListener('change', () => {
            this.send({ h_dag_jobb: this.hDagBox.checked });
        });
        document.getElementById('redusertNullstill')
            .addEventListener('click', () => this.nullstill());
        // Capture phase, so a click on a shift doesn't also open the strekliste
        // modal. Every other click passes through untouched.
        document.body.addEventListener('click', (event) => this.handleClick(event), true);
    }

    toggleSelecting() {
        this.selecting = !this.selecting;
        this.container.classList.toggle('vakt-velger-aktiv', this.selecting);
        this.velgButton.textContent = this.selecting ? 'Ferdig' : 'Velg vakter';
        this.velgButton.setAttribute('aria-pressed', String(this.selecting));
    }

    handleClick(event) {
        if (!this.selecting) return;
        const cell = event.target.closest('td[data-vakt]');
        if (!cell) return;
        event.preventDefault();
        event.stopPropagation();

        const vakt = cell.dataset.vakt;
        const current = this.wanted.has(vakt) ? this.wanted.get(vakt) : this.removed.has(vakt);
        this.wanted.set(vakt, !current);
        this.send({ vakt, fjernet: !current });
    }

    saveProsent() {
        if (this.prosentInput.validity.badInput) {
            this.showError('Prosent må være et tall mellom 1 og 100.');
            this.prosentInput.value = this.savedProsent;
            return;
        }
        const value = this.prosentInput.value.trim();
        this.send({ prosent: value === '' ? null : Number(value) });
    }

    nullstill() {
        if (!window.confirm('Vil du nullstille planen? Prosent, valgte vakter og H-dag blir nullstilt.')) return;
        this.send({ nullstill: true }, () => window.location.reload());
    }

    send(change, afterSuccess) {
        this.waiting += 1;
        this.queue = this.queue
            .then(() => this.post(change))
            .then((data) => {
                this.render(data);
                if (afterSuccess) afterSuccess();
            })
            .catch((error) => {
                // Keep the state the page already shows. Later requests still run.
                if (change.vakt) this.wanted.delete(change.vakt);
                this.prosentInput.value = this.savedProsent;
                if (this.hDagBox) this.hDagBox.checked = this.savedHdag;
                this.showError(error.message);
            })
            .finally(() => {
                this.waiting -= 1;
                if (this.waiting === 0) this.wanted.clear();
            });
    }

    async post(change) {
        let response;
        let data;
        try {
            response = await apiFetch(ROUTE, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sett: this.turnusSetId, ...change }),
            });
            // Not JSON if the session expired and this redirected to the login page.
            data = await response.json();
        } catch {
            throw new Error(SAVE_FAILED);
        }
        if (!response.ok || data.status !== 'success') {
            throw new Error(data.message || SAVE_FAILED);
        }
        return data;
    }

    render(data) {
        const summary = data.summary;
        this.removed = new Set(data.fjernet);
        document.querySelectorAll('[data-vakt]').forEach((element) => {
            element.classList.toggle('vakt-fjernet', this.removed.has(element.dataset.vakt));
        });
        if (this.hDagBox) {
            this.hDagBox.checked = summary.h_dag_jobb;
            this.hDagBox.disabled = summary.helg_varsel;
            this.savedHdag = summary.h_dag_jobb;
            document.querySelectorAll('[data-h-dag]').forEach((element) => {
                element.classList.toggle('vakt-h-fri', !summary.h_dag_jobb);
            });
        }
        document.getElementById('redusertHelgVarsel')
            ?.classList.toggle('d-none', !summary.helg_varsel);

        // The hours left show once a shift is removed, Totalt and Mål only with a target.
        const hasTarget = summary.prosent !== null;
        this.panel.querySelector('.redusert-tall')
            .classList.toggle('d-none', !hasTarget && this.removed.size === 0);
        this.panel.querySelectorAll('.redusert-mal').forEach((element) => {
            element.classList.toggle('d-none', !hasTarget);
        });
        const underVarsel = document.getElementById('redusertUnderVarsel');
        underVarsel.textContent = summary.under_varsel;
        underVarsel.classList.toggle('d-none', !summary.under_varsel);

        this.setText('total', summary.total);
        this.setText('target', summary.target || '–');
        this.setText('remaining', summary.remaining);
        this.setText('status', summary.status);
        this.savedProsent = summary.prosent === null ? '' : String(summary.prosent);
        // A placeholder, not a value: it isn't a target, and the browser hides
        // it as soon as the driver types one.
        this.prosentInput.placeholder = summary.beregnet_prosent;

        const note = document.getElementById('calUtelatt');
        if (note) {
            note.classList.toggle('d-none', !summary.utelatt);
            note.querySelector('[data-utelatt]').textContent = summary.utelatt;
        }

        const table = this.panel.closest('.list-group-item')?.querySelector('table');
        if (table && this.postNightMarker) this.postNightMarker.refreshTable(table);

        this.errorBox.classList.add('d-none');
    }

    setText(name, value) {
        this.panel.querySelector(`[data-redusert="${name}"]`).textContent = value;
    }

    showError(message) {
        this.errorBox.textContent = message;
        this.errorBox.classList.remove('d-none');
    }
}
