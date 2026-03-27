// Onboarding tour step definitions for the Favorites page
// State-aware: returns different steps depending on whether the user has favorites.

export default function () {
  const hasFavorites = document.querySelector('.list-group-item') !== null;

  if (!hasFavorites) {
    // Path A: No favorites yet — show the empty state and how to get started
    return [
      {
        popover: {
          title: "Favoritter-siden",
          description: `
            <p>Her samler du turnusene du er mest interessert i.</p>
            <p>Favorittlisten lar deg <strong>prioritere</strong> turnusene og laste ned søknadsskjema basert på din prioritering.</p>
          `,
          side: "over",
          align: "center",
        },
      },
      {
        element: '.text-center.py-5',
        popover: {
          title: "Ingen favoritter ennå",
          description: `
            <p>Du har ikke lagt til noen favoritter ennå.</p>
            <p>Gå til <strong>turnuslisten</strong> og klikk på stjernen ved siden av en turnus for å legge den til her.</p>
          `,
          side: "bottom",
          align: "center",
        },
      },
      {
        element: 'a[href*="turnusliste"]',
        popover: {
          title: "Gå til turnuslisten",
          description: `
            <p>Klikk her for å gå til turnuslisten der du kan stjernemerk turnuser.</p>
            <p class="tour-hint">Du kan alltid komme tilbake hit etterpå.</p>
          `,
          side: "bottom",
          align: "start",
        },
      },
      {
        element: '.card.border-primary',
        popover: {
          title: "Generer automatisk",
          description: `
            <p>Har du favoritter fra et tidligere år? Bruk denne funksjonen for å finne turnuser som ligner mest på dem.</p>
            <p class="tour-hint">Nyttig når du skal velge for et nytt turnusår.</p>
          `,
          side: "top",
          align: "start",
        },
      },
    ];
  }

  // Path B: Has favorites — show how to use the list
  return [
    {
      popover: {
        title: "Favoritter-siden",
        description: `
          <p>Her ser du alle turnusene du har stjernemerket.</p>
          <p>Du kan <strong>sortere</strong> dem i prioritert rekkefølge og bruke listen som grunnlag for søknadsskjema.</p>
        `,
        side: "over",
        align: "center",
      },
    },
    {
      element: '.list-group-item',
      popover: {
        title: "Din favorittliste",
        description: `
          <p>Favorittene vises her i den rekkefølgen du har satt dem.</p>
          <p>Øverst er din <strong>høyest prioriterte</strong> turnus.</p>
        `,
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '.btn-group-vertical',
      popover: {
        title: "Endre rekkefølge",
        description: `
          <p>Bruk <strong>pil-knappene</strong> for å flytte en turnus opp eller ned i listen.</p>
          <p class="tour-hint">Rekkefølgen lagres automatisk.</p>
        `,
        side: "right",
        align: "start",
      },
    },
    {
      element: '.position-display',
      popover: {
        title: "Sett posisjon direkte",
        description: `
          <p>Klikk på <strong>nummeret</strong> (f.eks. #1) for å skrive inn ønsket plass direkte.</p>
          <p class="tour-hint">Praktisk hvis du vil flytte en turnus langt opp eller ned i listen.</p>
        `,
        side: "right",
        align: "start",
      },
    },
    {
      element: '.mb-3.no-print.d-flex',
      popover: {
        title: "Handlingsknapper",
        description: `
          <p><strong>Generer favorittliste</strong> — henter turnuser fra forrige år som ligner dine nåværende favoritter.</p>
          <p><strong>Last ned søknadsskjema</strong> — lager et Word-dokument med favorittene i prioritert rekkefølge.</p>
        `,
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '.custom-key-btn',
      popover: {
        title: "Turnusnøkkel",
        description: `
          <p>Klikk på <strong>nøkkelen</strong> for å åpne turnusnøkkelen for denne turnusen.</p>
          <p class="tour-hint">Nøkkelen viser den detaljerte dagsplanen for hvert skift.</p>
        `,
        side: "left",
        align: "start",
      },
    },
    {
      element: '.remove-favorite-btn',
      popover: {
        title: "Fjern favoritt",
        description: `
          <p>Klikk på <strong>søppelkassen</strong> for å fjerne en turnus fra favorittlisten.</p>
          <p class="tour-hint">Du kan alltid legge den til igjen fra turnuslisten.</p>
        `,
        side: "left",
        align: "start",
      },
    },
  ];
}
