// General app welcome — shown once ever, on whatever page the user first lands on.

export default function () {
    const isMobile = window.innerWidth < 992;

    const navMintur = isMobile
        ? document.querySelector('.mobile-icon-nav a[href*="mintur"]')
        : document.querySelector('#navbarNav a[href*="mintur"]');
    const navFav = isMobile
        ? document.querySelector('.mobile-icon-nav a[href*="favorites"]')
        : document.querySelector('#navbarNav a[href*="favorites"]');
    const navOversikt = isMobile
        ? document.querySelector('.mobile-icon-nav a[href*="oversikt"]')
        : document.querySelector('#navbarNav a[href*="oversikt"]');

    const helpBtn = document.getElementById("help-icon-btn");
    const helpVisible = helpBtn && helpBtn.style.display !== "none";

    const steps = [
        {
            popover: {
                title: "Velkommen til Turnushjelper! 👋",
                description: `
          <p>Denne guiden viser deg de viktigste funksjonene i appen.</p>
          <p>Turnushjelper lar deg:</p>
          <ul class="tour-list">
            <li>Se og sammenligne alle turnuser i ruteterminet</li>
            <li>Lagre favoritter og sette dem i prioritert rekkefølge</li>
            <li>Laste ned søknadsskjema basert på din prioritering</li>
          </ul>
          <p>Husk at du ALLTID må sjekke at turnusene her stemmer med de
          offisielle turnusene før du sender inn søknaden. Jeg tar ikke ansvar for eventuelle
          feil i turnusene.</p>
          <p class="tour-hint">Når du klikker <strong>Neste</strong> godtar du dette og starter omvisningen.</p>
        `,
                side: "over",
                align: "center",
            },
        },

        ...(navMintur
            ? [
                  {
                      element: isMobile
                          ? '.mobile-icon-nav a[href*="mintur"]'
                          : '#navbarNav a[href*="mintur"]',
                      popover: {
                          title: "Min Tur 🚂",
                          description: `
          <p>Her ser du <strong>din valgte turnus</strong> i detalj — skiftene dine dag for dag.</p>
          <p class="tour-hint">Tilgjengelig etter at turnus er valgt.</p>
        `,
                          side: "bottom",
                          align: "start",
                      },
                  },
              ]
            : []),

        ...(navFav
            ? [
                  {
                      element: isMobile
                          ? '.mobile-icon-nav a[href*="favorites"]'
                          : '#navbarNav a[href*="favorites"]',
                      popover: {
                          title: "Favoritter ⭐",
                          description: `
          <p>Her lagrer du turnusene du er mest interessert i.</p>
          <p>Du kan sette dem i <strong>prioritert rekkefølge</strong> og laste ned søknadsskjema basert på listen.</p>
        `,
                          side: "bottom",
                          align: "start",
                      },
                  },
              ]
            : []),

        ...(navOversikt
            ? [
                  {
                      element: isMobile
                          ? '.mobile-icon-nav a[href*="oversikt"]'
                          : '#navbarNav a[href*="oversikt"]',
                      popover: {
                          title: "Oversikt 📊",
                          description: `
          <p>Her finner du <strong>statistikk</strong> over alle turnusene — helgetimer, nattevakter, tidligvakter og mer.</p>
          <p class="tour-hint">Nyttig for å sammenligne turnuser på tvers.</p>
        `,
                          side: "bottom",
                          align: "start",
                      },
                  },
              ]
            : []),

        ...(helpVisible
            ? [
                  {
                      element: "#help-icon-btn",
                      popover: {
                          title: "Hjelp-knappen",
                          description: `
          <p>Klikk her når som helst for å åpne en guide for siden du er på.</p>
          <p class="tour-hint">Guiden er tilgjengelig på alle sider med denne knappen.</p>
        `,
                          side: "bottom",
                          align: "end",
                      },
                  },
              ]
            : []),
        // Step 7: User menu
        {
            element: ".user-menu-btn",
            popover: {
                title: "Brukermeny",
                description: `
                <p>Her finner du:</p>
                <ul class="tour-list">
                    <li><strong>Min Side</strong> — innstillinger og profil</li>
                    <li><strong>Last ned PDF</strong> — turnus som PDF</li>
                    <li><strong>Logg ut</strong></li>
                </ul>
                <p class="tour-hint">Administratorer finner også admin-panelet her.</p>
            `,
                side: "bottom",
                align: "end",
            },
        },
    ];

    return steps;
}
