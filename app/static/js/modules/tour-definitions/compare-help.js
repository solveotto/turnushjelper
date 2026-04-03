// Help guide step definitions for the Oversikt (compare) page

export default function () {
  const isMobile = window.innerWidth < 992;

  const steps = [
    {
      popover: {
        title: "Oversikt",
        description: `
          <p>Her kan du <strong>sammenligne statistikk</strong> på tvers av alle tilgjengelige turnuser.</p>
          <p>Du kan fremheve en turnus ved å klikke på den i en tabell, sortere kolonnene med menyen øverst, og bla nedover for vaktprofil og helgeprofil.</p>
          <p class="tour-hint">Har du vært innplassert tidligere vises det også øverst på siden.</p>
        `,
        side: "over",
        align: "center",
      },
    },
  ];

  const fridagerEl = document.querySelector('.section-fridager');
  if (fridagerEl) {
    steps.push({
      element: fridagerEl,
      popover: {
        title: "Fridager per ukedag",
        description: `
          <p>Tabellen viser antall <strong>fridager per ukedag</strong> for alle turnuser.</p>
        `,
        side: "bottom",
        align: "start",
      },
    });
  }

  const wdThEl = document.querySelector('.wd-th');
  if (wdThEl) {
    steps.push({
      element: wdThEl,
      popover: {
        title: "Sorter etter ukedag",
        description: `
          <p>Klikk på en ukedag — <strong>Man, Tir, Ons</strong> osv. — for å sortere tabellen etter antall fridager den dagen.</p>
        `,
        side: "bottom",
        align: "start",
      },
    });
  }

  const turnusLinkEl = document.querySelector('.modal-turnus-link');
  if (turnusLinkEl) {
    steps.push({
      element: turnusLinkEl,
      popover: {
        title: "Vis turnusen",
        description: `
          <p>Klikk på et <strong>turnus-navn</strong> i tabellen for å se en detaljert visning av den turnusen.</p>
        `,
        side: "right",
        align: "start",
      },
    });
  }

  return steps;
}
