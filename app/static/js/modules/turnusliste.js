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
    const toggleBtn = document.getElementById('favorites-toggle-btn');

    if (toggleBtn) {
        let hideFavorites = (localStorage.getItem('turnuslisteViewMode') || 'show-all') === 'hide-favorites';

        function updateToggleBtn() {
            if (hideFavorites) {
                toggleBtn.innerHTML = '<i class="bi bi-eye me-1"></i>Vis favoritter';
            } else {
                toggleBtn.innerHTML = '<i class="bi bi-eye-slash me-1"></i>Skjul favoritter';
            }
        }

        toggleFavoritesVisibility(hideFavorites);
        updateToggleBtn();

        toggleBtn.addEventListener('click', function() {
            hideFavorites = !hideFavorites;
            localStorage.setItem('turnuslisteViewMode', hideFavorites ? 'hide-favorites' : 'show-all');
            toggleFavoritesVisibility(hideFavorites);
            updateToggleBtn();
        });
    }

    // The .printable container holds the view state (CSS variable + class) so it
    // cascades to lazy-rendered tables automatically.
    const printable = document.querySelector('.printable');

    // Set up shift size slider
    const sizeSlider = document.getElementById('shift-size-slider');
    const sizeReset = document.getElementById('shift-size-reset');

    if (printable && sizeSlider) {
        function applyShiftScale(scale) {
            printable.style.setProperty('--shift-scale', scale);
            sizeSlider.value = scale;
            localStorage.setItem('turnuslisteShiftScale', scale);
        }

        applyShiftScale(localStorage.getItem('turnuslisteShiftScale') || '1');

        sizeSlider.addEventListener('input', function() {
            applyShiftScale(sizeSlider.value);
        });

        if (sizeReset) {
            sizeReset.addEventListener('click', function() {
                applyShiftScale('1');
            });
        }
    }

    // Set up columns slider (number of turnuses side by side, 1-4)
    const columnsSlider = document.getElementById('columns-slider');
    const columnsValue = document.getElementById('columns-value');

    if (printable && columnsSlider) {
        function applyColumns(cols) {
            cols = parseInt(cols, 10) || 1;
            columnsSlider.value = cols;
            if (columnsValue) columnsValue.textContent = cols;
            printable.style.setProperty('--turnus-cols', cols);
            printable.classList.toggle('multi-up', cols > 1);
            localStorage.setItem('turnuslisteColumns', cols);
        }

        applyColumns(localStorage.getItem('turnuslisteColumns') || '1');

        columnsSlider.addEventListener('input', function() {
            applyColumns(columnsSlider.value);
        });
    }

    // Set up hide-table toggle (shows only name on top + stats at the bottom)
    const hideTableBtn = document.getElementById('hide-table-toggle-btn');

    if (printable && hideTableBtn) {
        let hideTable = localStorage.getItem('turnuslisteHideTable') === '1';

        function updateHideTableBtn() {
            if (hideTable) {
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Vis tabell';
            } else {
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Skjul tabell';
            }
        }

        printable.classList.toggle('hide-table', hideTable);
        updateHideTableBtn();

        hideTableBtn.addEventListener('click', function() {
            hideTable = !hideTable;
            localStorage.setItem('turnuslisteHideTable', hideTable ? '1' : '0');
            printable.classList.toggle('hide-table', hideTable);
            updateHideTableBtn();
        });
    }

});

