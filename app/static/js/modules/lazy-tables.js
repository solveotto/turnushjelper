// Lazy Tables Module
// Uses IntersectionObserver to defer table rendering until each list item
// is about to scroll into view, reducing initial DOM size significantly.

export class LazyTables {
    constructor(shiftColors, postNightMarker) {
        this.shiftColors = shiftColors;
        this.postNightMarker = postNightMarker;
        this.observer = new IntersectionObserver(
            this.handleIntersect.bind(this),
            { rootMargin: '400px' }  // pre-load 400px before visible
        );
        document.querySelectorAll('.list-group-item').forEach(li => {
            if (li.querySelector('template[data-lazy-table]')) {
                this.observer.observe(li);
            }
        });
    }

    handleIntersect(entries) {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const li = entry.target;
            const template = li.querySelector('template[data-lazy-table]');
            if (!template) return;

            const placeholder = li.querySelector('.turnus-table-placeholder');
            if (placeholder) placeholder.remove();

            // replaceWith inserts the fragment at the template's exact DOM position,
            // preserving the order: table before .data-felt stats grid.
            template.replaceWith(template.content.cloneNode(true));

            // Apply shift colors to newly inserted cells
            if (this.shiftColors) this.shiftColors.applyColorsToRoot(li);
            // Mark post-night recovery days
            if (this.postNightMarker) {
                li.querySelectorAll('table').forEach(t => this.postNightMarker.processTable(t));
            }

            this.observer.unobserve(li);
        });
    }
}
