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


    return steps;
}
