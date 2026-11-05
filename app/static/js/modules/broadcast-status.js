// Follows a running send on the admin email page. Loaded only while it runs.

const POLL_INTERVAL_MS = 3000;

const panel = document.getElementById('broadcast-status');

async function poll() {
    let status;
    try {
        const response = await fetch(panel.dataset.statusUrl, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!response.ok) return;
        status = await response.json();
    } catch (error) {
        // A deploy or a dropped connection. The next poll tries again.
        console.error('Could not read the send status:', error);
        return;
    }

    // The buttons and the reason depend on the state, and the server renders those.
    if (status.state !== panel.dataset.state) {
        window.location.reload();
        return;
    }

    panel.querySelectorAll('[data-count]').forEach((element) => {
        element.textContent = status[element.dataset.count];
    });
    const stopButton = document.getElementById('broadcast-stop');
    if (stopButton) stopButton.disabled = status.stop_requested;
}

if (panel) {
    setInterval(poll, POLL_INTERVAL_MS);
}
