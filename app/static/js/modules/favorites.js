// Favorites Module
// Handles favorite toggle functionality

export class Favorites {
    constructor() {
        this.init();
    }

    init() {
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Use event delegation to handle change events on elements with the class 'toggle-favoritt'
        document.body.addEventListener('change', (event) => {
            if (event.target.classList.contains('toggle-favoritt')) {
                this.handleToggleFavorite(event);
            }
        });

        // Handle remove favorite button clicks (X buttons)
        document.body.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-favorite-btn')) {
                this.handleRemoveFavorite(event);
            }
        });
    }

    handleToggleFavorite(event) {
        const isChecked = event.target.checked;
        const shiftTitle = event.target.getAttribute('shift_title');

        this.updateFavoriteStatus(isChecked, shiftTitle);
    }

    handleRemoveFavorite(event) {
        const shiftTitle = event.target.getAttribute('data-shift-title');

        if (!shiftTitle) {
            console.error('No shift title found for remove button');
            return;
        }

        this.updateFavoriteStatus(false, shiftTitle)
            .then(data => {
                // Remove the favorite item from the page after successful removal
                if (data.status === 'success') {
                    const favoriteItem = event.target.closest('.list-group-item');
                    if (favoriteItem) {
                        favoriteItem.remove();
                    } else {
                        console.warn('Could not find favorite item to remove from page');
                    }
                } else {
                    console.error('Failed to remove favorite:', data.message);
                    alert('Feil ved fjerning av favoritt: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error removing favorite:', error);
                alert('Feil ved fjerning av favoritt');
            });
    }

    async updateFavoriteStatus(favorite, shiftTitle) {
        try {
            const requestData = { favorite: favorite, shift_title: shiftTitle };

            const response = await fetch('/api/toggle_favorite', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (data.status === 'success' && data.favorites !== undefined) {
                this.updateFavoritesDom(data.favorites, data.positions);
            }

            return data;
        } catch (error) {
            console.error('Error updating favorite status:', error);
            throw error;
        }
    }

    updateFavoritesDom(favorites, positions) {
        document.querySelectorAll('.list-group-item').forEach(li => {
            const checkbox = li.querySelector('.toggle-favoritt');
            if (!checkbox) return;

            const name = checkbox.getAttribute('shift_title');
            if (!name) return;

            const isFavorite = favorites.includes(name);

            // Toggle the favorite-item CSS class on the <li>
            li.classList.toggle('favorite-item', isFavorite);

            // Locate the header row (first .d-flex.justify-content-between inside the li)
            const headerRow = li.querySelector('.d-flex.align-items-center.justify-content-between');
            if (!headerRow) return;

            const existingBadge = headerRow.querySelector('.turnus-favorite-badge');

            if (isFavorite) {
                const position = positions[name];
                if (existingBadge) {
                    // Update the badge number
                    const pill = existingBadge.querySelector('.badge');
                    if (pill) pill.textContent = `#${position}`;
                } else {
                    // Create the badge and insert it as the second child (after the name div)
                    const badge = document.createElement('div');
                    badge.className = 'd-flex align-items-center gap-2 turnus-favorite-badge';
                    badge.innerHTML =
                        '<span class="text-muted small">Favoritt:</span>' +
                        `<span class="badge bg-primary rounded-pill">#${position}</span>`;
                    // Insert after the first child (name div)
                    const firstChild = headerRow.firstElementChild;
                    if (firstChild && firstChild.nextSibling) {
                        headerRow.insertBefore(badge, firstChild.nextSibling);
                    } else {
                        headerRow.appendChild(badge);
                    }
                }
            } else {
                // Remove badge if present
                if (existingBadge) existingBadge.remove();
            }
        });
    }
}
