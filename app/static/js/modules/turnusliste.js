// Highlight Navigation Module
// Handles highlighting and auto-scrolling to specific turnus items

// Global function for handling key button clicks
function handleKeyFunction(turnusName) {
    const turnusSetId = getCurrentTurnusSetId();
    if (!turnusSetId) { alert('Kunne ikke finne aktiv turnus-sett'); return; }
    window.open(`/turnusnokkel/${turnusSetId}/${encodeURIComponent(turnusName)}`, '_blank');
}

// Helper function to get current turnus set ID
function getCurrentTurnusSetId() {
    // Try to get from the printable container
    const printableContainer = document.querySelector('.printable');
    if (printableContainer && printableContainer.dataset.currentTurnusSetId) {
        const idValue = printableContainer.dataset.currentTurnusSetId;
        if (idValue === 'null' || idValue === null || idValue === '') {
            console.log('Turnus set ID is null or empty');
            return null;
        }
        const id = parseInt(idValue);
        console.log('Found turnus set ID from printable container:', id);
        return id;
    }
    
    // Try to get from hidden input
    const hiddenInput = document.querySelector('input[name="current_turnus_set_id"]');
    if (hiddenInput) {
        const id = parseInt(hiddenInput.value);
        console.log('Found turnus set ID from hidden input:', id);
        return id;
    }
    
    // Try to get from data attribute on body
    const body = document.body;
    if (body.dataset.currentTurnusSetId) {
        const id = parseInt(body.dataset.currentTurnusSetId);
        console.log('Found turnus set ID from body:', id);
        return id;
    }
    
    // Fallback: look for turnus set info in the page
    const turnusSetInfo = document.querySelector('[data-turnus-set-id]');
    if (turnusSetInfo) {
        const id = parseInt(turnusSetInfo.dataset.turnusSetId);
        console.log('Found turnus set ID from generic selector:', id);
        return id;
    }
    
    console.log('No turnus set ID found');
    return null;
}

// Toggle favorites visibility
// Uses a CSS class so the rule applies automatically to lazy-rendered tables too.
function toggleFavoritesVisibility(hideFavorites) {
    document.querySelectorAll('.favorite-item').forEach(item => {
        item.classList.toggle('favorites-hidden', hideFavorites);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // Resolve highlighted element. The server renders the class when the page
    // is not cached, but the route is cached without the ?turnus= param in the
    // key — so on cache hits the class is absent. Fall back to a client-side
    // lookup via the data-turnus attribute, which is always in the DOM.
    const urlTurnus = new URLSearchParams(location.search).get('turnus');
    let highlightedElement = document.querySelector('.highlighted-turnus');

    if (urlTurnus && !highlightedElement) {
        const div = document.querySelector(`[data-turnus="${CSS.escape(urlTurnus)}"]`);
        const li = div?.closest('li');
        if (li) {
            li.classList.add('highlighted-turnus');
            highlightedElement = li;
        }
    }

    if (highlightedElement) {
        // Jump to highlighted element
        setTimeout(() => {
            const rect = highlightedElement.getBoundingClientRect();
            const elementTop = rect.top + window.pageYOffset;
            const elementHeight = rect.height;
            const windowHeight = window.innerHeight;
            const scrollTo = elementTop - (windowHeight / 2) + (elementHeight / 2);

            window.scrollTo(0, scrollTo);
        }, 1000);

        // Remove highlight when clicking anywhere else
        document.addEventListener('click', function(event) {
            if (!highlightedElement.contains(event.target)) {
                highlightedElement.classList.remove('highlighted-turnus');
                const url = new URL(window.location);
                url.searchParams.delete('turnus');
                window.history.replaceState({}, '', url);
            }
        });
    }
    
    // Set up favorites toggle
    const hideFavoritesRadio = document.getElementById('hide-favorites');
    const showAllRadio = document.getElementById('show-all');
    
    if (hideFavoritesRadio && showAllRadio) {
        // Load saved preference from localStorage, default to 'show-all'
        const savedViewMode = localStorage.getItem('turnuslisteViewMode') || 'show-all';
        const hideFavorites = savedViewMode === 'hide-favorites';

        // Set the radio button state based on saved preference
        if (hideFavorites) {
            hideFavoritesRadio.checked = true;
            showAllRadio.checked = false;
        } else {
            showAllRadio.checked = true;
            hideFavoritesRadio.checked = false;
        }

        // Apply the saved state
        toggleFavoritesVisibility(hideFavorites);

        // Add event listeners
        hideFavoritesRadio.addEventListener('change', function() {
            if (this.checked) {
                localStorage.setItem('turnuslisteViewMode', 'hide-favorites');
                toggleFavoritesVisibility(true);
            }
        });

        showAllRadio.addEventListener('change', function() {
            if (this.checked) {
                localStorage.setItem('turnuslisteViewMode', 'show-all');
                toggleFavoritesVisibility(false);
            }
        });
    }
});

