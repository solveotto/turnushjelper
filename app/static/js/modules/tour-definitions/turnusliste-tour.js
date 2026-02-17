// Tour step definitions for the Turnusliste page
// Each step follows the Driver.js popover config format

export function getTurnuslisteTourSteps() {
  // Detect mobile vs desktop for the sorter button selector
  const isMobile = window.innerWidth < 992;

  return [
    {
      // Step 1: Welcome (centered, no element)
      popover: {
        title: "Velkommen til Turnuslisten! 👋",
        description: `
                    <p>Denne guiden viser deg de viktigste funksjonene på denne siden.</p>
                    <p>Her kan du se alle turnuser, sortere dem etter dine preferanser,
                    og lagre favoritter for å sortere den prioriterte rekkefølgen.</p>
                    <p class="tour-hint">Klikk <strong>Neste</strong> for å starte omvisningen.</p>
                `,
        side: "over",
        align: "center",
      },
    },
    {
      // Step 2: Sort/Filter system
      element: isMobile ? ".mobile-sorter-btn" : ".sorter-btn",
      popover: {
        title: "Sortering og filtrering",
        description: `
                    <p>Bruk filteret for å sortere turnusene etter det som er viktigst for deg.</p>
                    <p>Du kan justere glidebrytere for:</p>
                    <ul class="tour-list">
                        <li><strong>Helgetimer</strong> — antall timer i helgen</li>
                        <li><strong>Nattevakter</strong> — antall nattskift</li>
                        <li><strong>Tidligvakter</strong> — skift som starter tidlig</li>
                        <li>...og flere kriterier</li>
                    </ul>
                    <p class="tour-hint">Dra glideren mot høyre for å prioritere turnuser med <em>mange</em> av den typen.</p>
                `,
        side: isMobile ? "bottom" : "bottom",
        align: "start",
      },
    },
    {
      // Step 3: Favorites
      element: ".custom-checkbox",
      popover: {
        title: "Favoritter ⭐",
        description: `
                    <p>Klikk på <strong>stjernen</strong> for å legge til en turnus i favorittlisten din.</p>
                    <p>Favorittene dine vises på en egen side der du sette dem i prioritert rekkefølge.</p>
                    <p class="tour-hint">Du kan endre rekkefølgen på favoritter etter at du har lagt til dem.</p>
                `,
        side: "left",
        align: "start",
      },
    },
    {
      // Step 4: Dobbelttur (centered, no element — informational)
      popover: {
        title: "Dobbelturer",
        description: `
                    <p>Noen turnuser har <strong>dobbelturer</strong> — to skift rett etter hverandre.</p>
                    <div class="tour-visual-example">
                        <div class="tour-example-cell tour-consecutive-arrow">
                            <span class="tour-example-label">3139</span>
                            <span class="tour-example-time">16:18 - 20:48</span>
                        </div>
                        <span class="tour-arrow-icon">→</span>
                        <div class="tour-example-cell tour-consecutive-receiver">
                            <span class="tour-example-label">3140</span>
                            <span class="tour-example-time">07:01 - 14:33</span>
                        </div>
                    </div>
                    <p>Cellen med <strong>pil/markering</strong> viser at neste skift starter rett etter.</p>
                    <p class="tour-hint">Hvis du holder musen over pilen, vil du komme en pop-up.</p>
                `,
        side: "over",
        align: "center",
      },
    },
    {
      // Step 5: Delt dagsverk (centered, no element — informational)
      popover: {
        title: "Delte dagsverk",
        description: `
                    <p>Et <strong>delt dagsverk</strong> betyr at du jobber et skift med en pause imellom.</p>
                    <div class="tour-visual-example">
                        <div class="tour-example-cell tour-delt-dagsverk">
                            <span class="tour-example-label">3144 **</span>
                            <span class="tour-example-time">20:23 - 08:28</span>
                        </div>
                    </div>
                    <p>Disse cellene er markert med <strong>**</strong> i tabellen.</p>
                    <p class="tour-hint">Det vil også her komme en pop-up som indikerer et delt dagsverk.</p>
                `,
        side: "over",
        align: "center",
      },
    },
    {
      // Step 6: Strekliste link
      element: ".dagsverk-link",
      popover: {
        title: "Streklister",
        description: `
                    <p>Klikk på <strong>dagsverk-nummeret</strong> (f.eks. 3007) for å se en visuell tidslinje for det skiftet.</p>
                    <p>Tidslinjen viser hele skiftet grafisk, slik at du raskt kan se start- og sluttider.</p>
                    <p class="tour-hint">Prøv å klikke på et dagsverk-nummer etter omvisningen!</p>
                `,
        side: "bottom",
        align: "start",
      },
    },
  ];
}
