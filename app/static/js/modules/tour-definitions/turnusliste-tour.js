// Tour step definitions for the Turnusliste page
// Each step follows the Driver.js popover config format

// Creates a temporary absolutely-positioned div spanning both dobbeltur cells
// so Driver.js can highlight them as a single unit. Caller must remove it via onDeselected.
function createDobbelturHighlight() {
    const arrow = document.querySelector(".consecutive-shift-arrow");
    if (!arrow) return null;
    const receiver = arrow.nextElementSibling;
    if (!receiver?.classList.contains("consecutive-shift-receiver"))
        return null;

    const ar = arrow.getBoundingClientRect();
    const rr = receiver.getBoundingClientRect();
    const el = document.createElement("div");
    el.id = "tour-dobbeltur-highlight";
    el.style.cssText = [
        "position:absolute",
        `top:${ar.top + window.scrollY}px`,
        `left:${ar.left + window.scrollX}px`,
        `width:${rr.right - ar.left}px`,
        `height:${ar.height}px`,
        "pointer-events:none",
        "z-index:0",
    ].join(";");
    document.body.appendChild(el);
    return el;
}

export default function () {
    const isMobile = window.innerWidth < 992;
    const dobbelturEl = isMobile ? null : createDobbelturHighlight();
    const firstDobbeltur =
        dobbelturEl ?? document.querySelector(".consecutive-shift-arrow");
    const firstDeltDagsverk = document.querySelector(".delt-dagsverk");
    const statsEl = document.querySelector(".data-felt");

    return [
        {
            // Step 2: Shift color legend (centered, no element — informational)
            // element: ".list-group-item",
            popover: {
                title: "Turnuslisten",
                description: `
                      <p>Dette er <strong>turnsene</strong> i ruteterminet.</p>
                      <p><strong>Cellefargene</strong> viser når på dagen skiftet starter:</p>
                      <div class="tour-color-legend">
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#87ceeb;"></span><span>Tidligvakt — starter før 06:00</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#4a90d9;"></span><span>Morgenvakt — starter mellom 06:00–07:59</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#637abf;"></span><span>Dagvakt — starter mellom 08:00–11:59</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#ff9999;"></span><span>Kveldsvakt — starter etter 12:00</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#af57eb;"></span><span>Nattevakt</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#4ade80;"></span><span>Fridag</span></div>
                          <div class="tour-color-row"><span class="tour-color-swatch" style="background:#fcd34d;"></span><span>H - Dag</span></div>
                      </div>
                      <p class="tour-hint">Underst i tabellen finner du <strong>en oversikt</strong> over innholdet i hver turnus.</p>
                  `,
                side: "over",
                align: "start",
            },
      },


      ...(statsEl ? [{
          element: statsEl,
          popover: {
              title: "Statistikk",
              description: `
          <p>Her ser du nøkkeltall for din turnus: antall dagsverk, tidlig-/kveld-/nattskift, helgetimer og mer.</p>
        `,
              side: isMobile ? "bottom" : "right",
              align: "start",
          },
      }] : []),

      {
          // Step 8: Sort/Filter system
          element: isMobile ? ".mobile-sorter-btn" : ".navbar-filtering .sorter-btn",
          popover: {
              title: "Sorter turnuser",
              description: `
                  <p>Bruk glidebrytere for å sortere turnusene etter det som er viktigst for deg.</p>
                  <p>Du kan foreksempel justere:</p>
                  <ul class="tour-list">
                      <li><strong>Helgetimer</strong></li>
                      <li><strong>Nattevakter</strong></li>
                      <li><strong>Tidligvakter</strong></li>
                      <li><strong>Kveldsvakter</strong></li>
                      <li>...og flere kriterier</li>
                  </ul>
                  <p class="tour-hint">Du kan velge <strong>flere kriterier</strong> samtidig.</p>
              `,
              side: isMobile ? "bottom" : "bottom",
              align: isMobile ? "start" : "end",
          },
      },


      ...(!isMobile && document.getElementById("gen-favorites-btn") ? [{
          element: "#gen-favorites-btn",
          popover: {
              title: "Generer favorittliste ✨",
              description: `
                  <p>Klikk her for å <strong>generere en favorittliste automatisk</strong>.</p>
                  <p>Verktøyet analyserer turnusene og finner de som ligner mest på dine favoritter fra tidligere år.</p>
                  <p class="tour-hint">Nyttig hvis du vil ha et godt utgangspunkt for søknaden uten å gå gjennom alle turnusene manuelt.</p>
              `,
              side: "bottom",
              align: isMobile ? "start" : "end",
          },
      }] : []),

      {
            // Turnsnøkkel
            element: ".custom-key-btn",
            popover: {
                title: "Turnusnøkkel 🔑",
                description: `
                    <p>Klikk på <strong>nøkkelen</strong> for å se turnusnøkelen for den aktuelle turnus.</p>
                    <p class="tour-hint">Her kan du velge rekkefølgen på linjene du søker og om du vil jobbe H-dag. De vil automatisk bli lagt til søknadskjema.</p>
                `,
                side: isMobile ? "bottom" : "left",
                align: "start",
            },
        },

        {
            // Step 9: Favorites star
            element: ".custom-checkbox",
            popover: {
                title: "Favoritter ⭐",
                description: `
                    <p>Klikk på <strong>stjernen</strong> for å legge til en turnus i favorittlisten din.</p>
                    <p>Favorittene dine vises på en egen side der du sette dem i prioritert rekkefølge.</p>
                    <p class="tour-hint">Du kan endre rekkefølgen på favoritter etter at du har lagt til dem.</p>
                `,
                side: isMobile ? "bottom" : "left",
                align: "start",
            },
        },

        {
            // Step 12: Strekliste link
            element: ".dagsverk-link",
            popover: {
                title: "Streklister 📝",
                description: `
                    <p>Klikk på <strong>dagsverk-nummeret</strong> (f.eks. 3007) for å se streklisten for det skiftet.</p>
                    <p class="tour-hint">Prøv å klikke på et dagsverk-nummer etter omvisningen!</p>
                `,
                side: "bottom",
                align: "start",
            },
        },

        {
            // Step 10: Dobbelttur — highlights both cells via temp wrapper, or single cell, or centered fallback
            ...(dobbelturEl
                ? { element: "#tour-dobbeltur-highlight" }
                : firstDobbeltur
                  ? { element: ".consecutive-shift-arrow" }
                  : {}),
            popover: {
                title: "Dobbelturer",
                description: `
                    <p>Noen turnuser har <strong>dobbelturer</strong> — to skift rett etter hverandre.</p>
                    ${firstDobbeltur ? "" : '<img src="/static/img/tour/dobbeltur.png" style="max-width:100%; border-radius:6px; margin:8px 0;">'}
                    <p>Cellen med <strong>pil/markering</strong> viser at neste skift starter rett etter.</p>
                    <p class="tour-hint">Hvis du holder musen over pilen, vil du komme en pop-up.</p>
                `,
                side: firstDobbeltur ? "bottom" : "over",
                align: "start",
            },
        },
        {
            // Step 11: Delt dagsverk — highlights real cell if present, else centered fallback
            ...(firstDeltDagsverk ? { element: ".delt-dagsverk" } : {}),
            popover: {
                title: "Delte dagsverk",
                description: `
                    <p>Et <strong>delt dagsverk</strong> betyr at du jobber et skift med en mindre betalt pause i dagsverket.</p>
                    ${firstDeltDagsverk ? "" : '<img src="/static/img/tour/deltdagsverk.png" style="display:block; margin:8px auto; max-width:25%; border-radius:2px;">'}
                    <p>Disse cellene er markert med <strong>**</strong> i tabellen.</p>
                    <p class="tour-hint">Det vil også her komme en pop-up som indikerer et delt dagsverk.</p>
                `,
                side: firstDeltDagsverk ? "bottom" : "over",
                align: "start",
            },
        },




    ];
}
