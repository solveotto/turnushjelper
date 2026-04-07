// Onboarding tour step definitions for the Min Tur page

export default function () {
    const isMobile = window.innerWidth < 992;

    const steps = [];

    // Schedule table — prefer the rendered table, fall back to placeholder
    const tableEl =
        document.querySelector(".table-scroll-wrapper") ||
        document.querySelector(".turnus-table-placeholder");
    if (tableEl) {
        steps.push({
            element: tableEl,
            popover: {
                title: "Min Tur",
                description: `
                <p>Her ser du <strong>din turnus</strong> dag for dag gjennom hele ruteterminet.</p>
                <p>Tabellen er organisert med uker som rader og ukedager som kolonner. Hver celle viser skiftet du jobber den dagen.</p>
                <p class="tour-hint">Cellefargene følger samme fargekode som i turnuslisten.</p>
        `,
                side: isMobile ? "bottom" : "bottom",
                align: "center",
            },
        });
    }

    const dagsverkEl = document.querySelector(".shift-timeline-trigger");
    if (dagsverkEl) {
        steps.push({
            element: dagsverkEl,
            popover: {
                title: "Strekliste",
                description: `
          <p>Klikk på et <strong>dagsverknummer</strong> i tabellen for å åpne streklisten for det dagsverk.</p>
          <p class="tour-hint">Streklisten viser inneholdet iskiftet.</p>
        `,
                side: "bottom",
                align: "center",
            },
        });
    }

    const statsEl = document.querySelector(".data-felt");
    if (statsEl) {
        steps.push({
            element: statsEl,
            popover: {
                title: "Statistikk",
                description: `
          <p>Her ser du nøkkeltall for din turnus: antall dagsverk, tidlig-/kveld-/nattskift, helgetimer og mer.</p>
          <p class="tour-hint">Tallene er beregnet over hele turnusperioden.</p>
        `,
                side: isMobile ? "bottom" : "right",
                align: "start",
            },
        });
    }

    const nokkelEl = document.querySelector("h5.mt-4");
    if (nokkelEl) {
        steps.push({
            element: nokkelEl,
            popover: {
                title: "Turnusnøkkel",
                description: `
          <p>Under tabellen finner du <strong>turnusnøkkelen</strong> for din linje.</p>
          <p>Nøkkelen viser hvilke dagsverk som er planlagt for hvert skift gjennom rotasjonen.</p>
        `,
                side: "bottom",
                align: "start",
            },
        });
    }

    return steps;
}
