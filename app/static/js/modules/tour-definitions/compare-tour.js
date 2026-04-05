// Onboarding tour step definitions for the Oversikt (compare) page

export default function () {
    const isMobile = window.innerWidth < 992;

    const steps = [
        {
            popover: {
                title: "Oversikt",
                description: `
          <p>Her kan du <strong>sammenligne statistikk</strong> på tvers av alle tilgjengelige turnuser.</p>
          <p class="tour-hint">Har du vært innplassert tidligere vises det også øverst på siden.</p>
        `,
                side: "over",
                align: "center",
            },
        },
    ];

    const fridagerEl = document.querySelector(".section-fridager");
    if (fridagerEl) {
        steps.push({
            element: fridagerEl,
            popover: {
                title: "Fridager per ukedag",
                description: `
                <p>Et eksempel er tabellen for fridager per ukedag.</p>
                <p>Tabellen viser hvor mange <strong>fridager</strong> det er på hver enkelt ukedag.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    const wdThEl = document.querySelector(".wd-th");
    if (wdThEl) {
        steps.push({
            element: wdThEl,
            popover: {
                title: "Sorter etter ukedag",
                description: `
          <p>Klikk på en ukedag — <strong>Man, Tir, Ons</strong> osv. — for å sortere tabellen etter antall fridager den dagen.</p>
          <p class="tour-hint">Nyttig hvis du ønsker fri på en bestemt ukedag.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    const turnusLinkEl = document.querySelector(
        ".weekday-grid .modal-turnus-link",
    );
    if (turnusLinkEl) {
        steps.push({
            element: turnusLinkEl,
            popover: {
                title: "Vis turnusen",
                description: `
          <p>Klikk på et <strong>turnus-navn</strong> i tabellene for å se en detaljert visning av den turnusen.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    return steps;
}
