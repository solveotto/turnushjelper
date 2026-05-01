// Tour step definitions for the Søknadsskjema page

export default function () {
    const isMobile = window.innerWidth < 992;
    const kol2El = document.querySelector('.toggle-cell[data-field="linje_135"]');
    const kol3El = document.querySelector('.priori-cell');
    const kol4El = document.querySelector('.toggle-cell[data-field="h_dag"]');

    return [
        {
            popover: {
                title: "Søknadsskjema",
                description: `
                    <p>Her fyller du ut og laster ned søknadsskjemaet for turplassering.</p>
                    <p class="tour-hint">Favorittene dine fra turnuslisten er allerede lagt inn i skjemaet.</p>
                `,
                side: "over",
                align: "start",
            },
        },
        {
            element: ".info-table",
            popover: {
                title: "Dine opplysninger",
                description: `
                    <p>Fyll inn dato, rullenummer og navn, og stasjoneringssted.</p>
                    <p class="tour-hint">Feltene er forhåndsutfylt med informasjon fra profilen din.</p>
                `,
                side: "bottom",
                align: "start",
            },
        },
        ...(kol2El ? [{
            element: '.toggle-cell[data-field="linje_135"]',
            popover: {
                title: "Kolonne 2 — Linjepeferanse",
                description: `
                    <p>Klikk for å velge hvilken <strong>helgegruppe</strong> du foretrekker — linje 1,3,5 eller linje 2,4,6.</p>
                    <p class="tour-hint">Du kan bare velge én av de to.</p>
                `,
                side: "bottom",
                align: "start",
            },
        }] : []),
        ...(kol3El ? [{
            element: '.priori-cell',
            popover: {
                title: "Kolonne 3 — Linjeprioritering",
                description: `
                    <p>Denne kolonnen fylles ut <strong>automatisk</strong> når du velger linjer i turnusnøkkelen for den aktuelle turnusen.</p>
                    <p class="tour-hint">Åpne turnusnøkkelen fra turnuslisten eller favorittlisten for å sette linjeprioritering.</p>
                `,
                side: "bottom",
                align: "start",
            },
        }] : []),
        ...(kol4El ? [{
            element: '.toggle-cell[data-field="h_dag"]',
            popover: {
                title: "Kolonne 4 — H-dag",
                description: `
                    <p>Klikk her hvis du ønsker å <strong>jobbe H-dag</strong> for denne turnusen.</p>
                    <p class="tour-hint">Blankt felt betyr fri på H-dager.</p>
                `,
                side: "bottom",
                align: "start",
            },
        }] : []),
        {
            element: '#skjema-download-buttons',
            popover: {
                title: "Last ned eller skriv ut",
                description: `
                    <p>Last ned skjemaet som <strong>.docx</strong> eller <strong>.pdf</strong>, eller <strong>skriv ut</strong> direkte.</p>
                `,
                side: "bottom",
                align: "center",
            },
        },
    ];
}
