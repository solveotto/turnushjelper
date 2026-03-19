// Help guide step definitions for the Favorites page
// Used both standalone (via help button) and as a cross-page continuation
// from turnusliste-help.js.

export default function () {
  const favoritesList = document.querySelector('.favorites-list, [data-favorites-list], .list-group');
  const dragHandle = document.querySelector('.drag-handle, [data-drag-handle]');
  const removeBtn = document.querySelector('.remove-favorite, [data-remove-favorite]');

  return [
    {
      popover: {
        title: "Favoritter-siden",
        description: `
                  <p>Her ser du alle turnusene du har stjernemerket.</p>
                  <p>Du kan <strong>sortere</strong> dem i prioritert rekkefølge og bruke listen som en huskelapp når du skal velge turnus.</p>
              `,
        side: "over",
        align: "center",
      },
    },
    {
      ...(favoritesList ? { element: '.favorites-list, [data-favorites-list], .list-group' } : {}),
      popover: {
        title: "Din favorittliste",
        description: `
                  <p>Favorittene vises her i den rekkefølgen du har satt dem.</p>
                  <p>Øverst er din <strong>høyest prioriterte</strong> turnus.</p>
              `,
        side: favoritesList ? "bottom" : "over",
        align: "start",
      },
    },
    {
      ...(dragHandle ? { element: '.drag-handle, [data-drag-handle]' } : {}),
      popover: {
        title: "Endre rekkefølge",
        description: `
                  <p>Dra i <strong>håndtaket</strong> (☰) for å flytte en turnus opp eller ned i listen.</p>
                  <p class="tour-hint">Rekkefølgen lagres automatisk.</p>
              `,
        side: dragHandle ? "right" : "over",
        align: "start",
      },
    },
    {
      ...(removeBtn ? { element: '.remove-favorite, [data-remove-favorite]' } : {}),
      popover: {
        title: "Fjern favoritt",
        description: `
                  <p>Klikk på <strong>søppelkassen</strong> eller stjernen igjen for å fjerne en turnus fra favorittlisten.</p>
                  <p class="tour-hint">Du kan alltid legge den til igjen fra turnuslisten.</p>
              `,
        side: removeBtn ? "left" : "over",
        align: "start",
      },
    },
  ];
}
