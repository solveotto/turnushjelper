// Onboarding tour step definitions for the Oversikt (compare) page

export default function () {
    const isMobile = window.innerWidth < 992;

    const steps = [
        {
            popover: {
                title: "Oversikt",
                description: `
          <p>Her kan du <strong>sammenligne statistikk</strong> på tvers av alle tilgjengelige turnuser.</p>
          <p>Siden inneholder tabeller og diagrammer for vakttyper, helgetimer, fridager og mer.</p>
        `,
                side: "over",
                align: "center",
            },
        },
    ];

    const innplasseringEl = document.querySelector("#innplassering-section");
    if (innplasseringEl) {
        steps.push({
            element: "#innplassering-section",
            popover: {
                title: "Tidligere innplasseringer",
                description: `
          <p>Her ser du turnusene du har vært innplassert på tidligere.</p>
          <p>Klikk på en rad for å se den fulle turnusen fra det ruteterminet.</p>
          <p class="tour-hint">Nyttig som referanse når du skal velge ny turnus.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    const controlsEl = document.querySelector(".compare-controls");
    if (controlsEl) {
        steps.push({
            element: ".compare-controls",
            popover: {
                title: "Sortering",
                description: `
          <p>Bruk denne menyen for å sortere alle tabeller og diagrammer på siden.</p>
          <ul class="tour-list">
            <li><strong>Størst → Minst</strong> — høyeste verdier øverst</li>
            <li><strong>Minst → Størst</strong> — laveste verdier øverst</li>
            <li><strong>A → Å</strong> — alfabetisk etter turnus-navn</li>
          </ul>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

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

    const heatmapEl = document.querySelector(".section-vakttyper");
    if (heatmapEl) {
        steps.push({
            element: heatmapEl,
            popover: {
                title: "Vakttype & Helg",
                description: `
          <p>Denne tabellen viser en samlet oversikt over vakttyper og helgearbeid for alle turnuser.</p>
          <ul class="tour-list">
            <li><strong>Natt, Tidlig, Ettm</strong> — antall skift av hver vakttype</li>
            <li><strong>Helg-t / Helg-d</strong> — helgetimer og helgedager</li>
            <li><strong>N-helg</strong> — nattevakter i helgen</li>
          </ul>
          <p class="tour-hint">Klikk på en kolonneoverskrift for å sortere tabellen etter den verdien.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    const vaktprofilEl = document.querySelector("#wrap-vaktprofil");
    if (vaktprofilEl) {
        steps.push({
            element: vaktprofilEl,
            popover: {
                title: "Vaktprofil",
                description: `
          <p>Diagrammet viser <strong>fordelingen av vakttyper</strong> for hver turnus som 100 % stablede søyler.</p>
          <p>Lengden på hver farge viser andelen natt-, tidlig- og ettermiddagsvakter relativt til hverandre.</p>
          <p class="tour-hint">Nyttig for å raskt se hvilke turnuser som domineres av én vakttype.</p>
        `,
                side: "top",
                align: "start",
            },
        });
    }

    const helgprofilEl = document.querySelector(".section-helg");
    if (helgprofilEl) {
        steps.push({
            element: helgprofilEl,
            popover: {
                title: "Helgeprofil",
                description: `
          <p>Her ser du fordelingen av <strong>helgearbeid</strong> — dagtid versus kveld/natt — for hver turnus.</p>
          <p class="tour-hint">Nyttig hvis tidspunktet for helgearbeid er viktig for deg.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    return steps;
}
