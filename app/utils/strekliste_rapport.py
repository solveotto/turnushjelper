"""A review report for the parsed strekliste: every duty's PNG beside the
rows the parser read from it, warnings first, in one HTML file.

Pure: duty dicts in (the shape strekliste_service.hent_dagsverk returns),
HTML out. Nothing here is served by the app; the file is for an admin to
open in a browser and read through before trusting the parse.
"""

import html
import os
import re

_KOLONNER = ("Fra", "Til", "Stasjoner", "Type", "Tog", "Tekst")

_STIL = """
body{font-family:system-ui,sans-serif;margin:1rem 2rem;color:#111}
h1{font-size:1.4rem} h2{font-size:1.1rem;margin:0 0 .3rem}
nav{font-size:.85rem;line-height:1.8;margin-bottom:1rem}
nav a{margin-right:.6rem;white-space:nowrap}
nav a.adv{color:#b00}
section.dagsverk{border-top:2px solid #ccc;padding:1rem 0;page-break-inside:avoid}
section.dagsverk img{max-width:100%;border:1px solid #ddd;display:block;margin:.4rem 0}
.meta{color:#555;font-size:.9rem}
.adv{color:#b00}
ul.advarsler{margin:.3rem 0;padding-left:1.2rem;color:#b00}
table{border-collapse:collapse;font-size:.85rem;margin-top:.4rem}
th,td{border:1px solid #ddd;padding:.15rem .5rem;text-align:left;vertical-align:top}
td.mono,th.mono{font-family:ui-monospace,monospace}
tr.neste td{background:#f4f4ff}
td.tog{font-weight:600}
.mangler{color:#b00;font-weight:600}
"""


def _nokkel(navn):
    return re.sub(r"[^0-9a-zæøå]", "", navn.lower())


def bildeoppslag(png_dir):
    """nr -> PNG file name, matched on letters and digits only: the PNG
    generator writes "3049!.png" and "5002-bm73-_F_N05_5.png" where the
    parser says "3049" and "5002-bm73-F_N05_5"."""
    try:
        filer = {_nokkel(f[:-4]): f for f in os.listdir(png_dir) if f.lower().endswith(".png")}
    except OSError:
        filer = {}
    return lambda nr: filer.get(_nokkel(nr))


def _e(v):
    return html.escape("" if v is None else str(v))


def _tid(a, felt):
    t = a.get(felt) or "?"
    return t + ("⁺" if a.get(f"{felt.split('_')[0]}_neste_dag") else "")


def _aktivitet_rad(a):
    klasse = ' class="neste"' if a.get("fra_neste_dag") else ""
    return (
        f"<tr{klasse}><td class=\"mono\">{_e(_tid(a, 'fra_tid'))}</td>"
        f"<td class=\"mono\">{_e(_tid(a, 'til_tid'))}</td>"
        f"<td class=\"mono\">{_e(a.get('fra_stasjon'))} → {_e(a.get('til_stasjon'))}</td>"
        f"<td>{_e(a.get('type'))}"
        + (f" <span class=\"meta\">({_e(a.get('monster'))})</span>"
           if a.get("monster") and a.get("monster") != a.get("type") else "")
        + f"</td><td class=\"mono tog\">{_e((a.get('tognumre') or '').replace(',', ' '))}</td>"
        f"<td class=\"mono\">{_e(a.get('tekst'))}</td></tr>"
    )


def _seksjon(d, png_dir_rel, finn_bilde):
    nr = d["nr"]
    anker = f"dv-{nr}-{d.get('kjoredager') or ''}".rstrip("-")
    bilde = finn_bilde(d.get("dobbelt_tur") or nr) or finn_bilde(nr)
    if bilde:
        bilde_html = f'<img src="{_e(png_dir_rel + "/" + bilde)}" alt="Strek {_e(nr)}">'
    else:
        bilde_html = '<p class="mangler">Bilde mangler (ingen PNG for dette nummeret)</p>'
    advarsler = d.get("advarsler") or []
    adv_html = ""
    if advarsler:
        adv_html = "<ul class=\"advarsler\">" + "".join(f"<li>{_e(w)}</li>" for w in advarsler) + "</ul>"
    rader = "".join(_aktivitet_rad(a) for a in d.get("aktiviteter", []))
    hode = "".join(f"<th>{k}</th>" for k in _KOLONNER)
    return (
        f'<section class="dagsverk" id="{_e(anker)}">'
        f"<h2>{_e(nr)} <span class=\"meta\">kjøredager {_e(d.get('kjoredager'))} · "
        f"{_e(d.get('start'))}–{_e(d.get('slutt'))}{'⁺' if d.get('slutt_neste_dag') else ''} · "
        f"{_e(d.get('materiell'))} · side {_e(d.get('side'))}"
        + (f" · dobbelt tur {_e(d['dobbelt_tur'])}" if d.get("dobbelt_tur") else "") + "</span></h2>"
        f"{adv_html}{bilde_html}"
        f"<table><thead><tr>{hode}</tr></thead><tbody>{rader}</tbody></table>"
        "</section>"
    )


def bygg_gjennomgang(dagsverk, png_dir, tittel, png_dir_rel="png"):
    """The whole report as an HTML string. Duties with warnings first, then
    the rest in page order; a jump list at the top links to every duty.

    ``png_dir`` is where the PNGs are (to know which exist); ``png_dir_rel``
    is how the report refers to them, relative to where it is written.
    """
    med = [d for d in dagsverk if d.get("advarsler")]
    uten = [d for d in dagsverk if not d.get("advarsler")]

    def lenke(d, klasse=""):
        anker = f"dv-{d['nr']}-{d.get('kjoredager') or ''}".rstrip("-")
        return f'<a href="#{_e(anker)}"{klasse}>{_e(d["nr"])}</a>'

    nav = (
        f"<nav><strong>Med advarsler ({len(med)}):</strong> "
        + " ".join(lenke(d, ' class="adv"') for d in med)
        + f"<br><strong>Uten advarsler ({len(uten)}):</strong> "
        + " ".join(lenke(d) for d in uten)
        + "</nav>"
    )
    finn_bilde = bildeoppslag(png_dir)
    seksjoner = "".join(_seksjon(d, png_dir_rel, finn_bilde) for d in med + uten)
    return (
        "<!DOCTYPE html>\n<html lang=\"no\"><head><meta charset=\"utf-8\">"
        f"<title>Gjennomgang strekliste {_e(tittel)}</title><style>{_STIL}</style></head><body>"
        f"<h1>Gjennomgang av streklisten {_e(tittel)}</h1>"
        f"<p class=\"meta\">{len(dagsverk)} dagsverk, {sum(len(d.get('aktiviteter', [])) for d in dagsverk)} "
        "aktiviteter. Sjekk stasjonspar per strekning, tognumre på Tilsyn/Skjøting/Deling, "
        "dagsverk over midnatt (⁺ = neste dag, blå rader), og typer der etiketten overstyrer mønsteret. "
        "Et nummer med flere kjøredager-varianter deler ett bilde.</p>"
        f"{nav}{seksjoner}</body></html>"
    )


def skriv_gjennomgang(dagsverk, png_dir, tittel, ut_sti):
    """Write the report next to the PNG folder so the image links resolve."""
    rel = os.path.relpath(png_dir, os.path.dirname(os.path.abspath(ut_sti)))
    innhold = bygg_gjennomgang(dagsverk, png_dir, tittel, png_dir_rel=rel.replace(os.sep, "/"))
    with open(ut_sti, "w", encoding="utf-8") as fh:
        fh.write(innhold)
    return ut_sti
