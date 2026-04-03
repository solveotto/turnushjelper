// Onboarding tour step definitions for the Min Tur page

export default function () {
  const isMobile = window.innerWidth < 992;

  const steps = [
    {
      popover: {
        title: "Min Tur",
        description: `
          <p>Her ser du <strong>din turnus</strong> — uke for uke gjennom hele turnusperioden.</p>
          <p>Siden viser også turnusnøkkelen og statistikk for din spesifikke linje.</p>
        `,
        side: "over",
        align: "center",
      },
    },
  ];

  // Schedule table — prefer the rendered table, fall back to placeholder
  const tableEl = document.querySelector('.table-scroll-wrapper') || document.querySelector('.turnus-table-placeholder');
  if (tableEl) {
    steps.push({
      element: tableEl,
      popover: {
        title: "Turnusplanen",
        description: `
          <p>Her vises turnusen uke for uke med dag- og tidspunkt for hvert skift.</p>
          <p>Klikk på et <strong>dagsverknummer</strong> i tabellen for å åpne streklisten for det dagsverk.</p>
        `,
        side: isMobile ? "bottom" : "right",
        align: "start",
      },
    });
  }

  const statsEl = document.querySelector('.data-felt');
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

  const dagsverkEl = document.querySelector('.dagsverk-link');
  if (dagsverkEl) {
    steps.push({
      element: dagsverkEl,
      popover: {
        title: "Strekliste",
        description: `
          <p>Klikk på et <strong>dagsverknummer</strong> i tabellen for å åpne streklisten for det dagsverk.</p>
          <p class="tour-hint">Streklisten viser alle tidspunkter og stopp for skiftet.</p>
        `,
        side: "bottom",
        align: "center",
      },
    });
  }

  const nokkelEl = document.querySelector('h5.mt-4');
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
