"""Read a Vy "Strekliste for Lokfører" PDF into duties and activities.

The strekliste is vector text, not a scan: every label sits at exact
coordinates, segment boundaries are drawn lines, and the activity *type* is a
tiled pattern image that the page's own legend also uses. So nothing here
guesses — every value is read off geometry, and every situation the rules do
not cover becomes a warning on the duty rather than an exception.

Pure: no database, no Flask. pdfplumber only.

Coordinates below are PDF points on the page as pdfplumber presents it (the
pages are stored rotated 90°; pdfplumber already returns visual coordinates).
The hour axis is computed per page and never hard-coded — the same generator
produces files with and without the Timer columns, and the axis width differs.
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

import pdfplumber

#: The nine "Timer" columns, in the order the header prints them.
TIMER_KOLONNER = ("KLT-NE", "P-AML", "GT-AML", "AML", "GT", "NT", "ST", "PASS", "Tj.t")

#: Legend labels as the PDF spells them → the name we store.
_LEGENDE_NAVN = {
    "Frammøte/Avsluttning": "Frammøte/Avslutning",
    "Kjøreing Opphold": "Kjøring opphold",
    "Dagsverk Opphold": "Dagsverk opphold",
}

_KJOREDAGER = re.compile(r"^[1-7]{1,7}$")
_TOG = re.compile(r"^\d{3,6}[A-Z]?$")
_STASJON = re.compile(r"^[A-ZÆØÅ]{2,5}$")
_MINUTT = re.compile(r"^\d{1,2}'$")
_KLOKKE = re.compile(r"^\d{1,2}:\d{2}$")
_TALL_I_TEKST = re.compile(r"(?<!\d)\d{3,6}[A-Z]?(?![a-zæøå\d])")

#: A label that names the activity outranks the pattern it is drawn with:
#: Tilsyn, Skjøting and Deling all use the Togaktivitet tile, Uttak and
#: Gangtid the Passreise tile. Longest first so "Til_plf" wins over "Til".
_NOKKELORD = (
    ("Skjøting", "Skjøting"), ("Skifting", "Skifting"), ("Passreise", "Passreise"),
    ("Innsett", "Innsett"), ("Gangtid", "Gangtid"), ("Fra/Ins", "Fra/Ins"),
    ("Til_plf", "Til_plf"), ("Tilsyn", "Tilsyn"), ("Deling", "Deling"),
    ("Reserve", "Reserve"), ("M-TAXI", "Taxi"), ("TAXI", "Taxi"), ("Taxi", "Taxi"),
    ("Inns", "Innsett"), ("Utt", "Uttak"),
)
_MARKOR = {"*": "Kjøring opphold", "**": "Dagsverk opphold"}

#: Where a leader tick under the bar sits, relative to the bar's top.
_TICK_AVSTAND = (5.0, 9.5)
_SUPERSKRIFT = 4.2
_DV_NR = re.compile(r"^\d{4,5}")

# Column edges of the left-hand cells (Nr. | Kjøredager | Materiell).
_X_NR_MAX = 44.0
_X_DAGER_MAX = 62.0


@dataclass
class Geometri:
    """The hour axis of one page: x → clock time."""

    h0: float
    pt_per_hour: float

    def minutter(self, x):
        return (x - self.h0) / self.pt_per_hour * 60

    def tid(self, x):
        m = int(round(self.minutter(x)))
        return f"{(m // 60) % 24:02d}:{m % 60:02d}"

    @property
    def h24(self):
        return self.h0 + 24 * self.pt_per_hour


@dataclass
class ParseResult:
    duties: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ── Page-level readers ─────────────────────────────────────────────────

def _ord(page):
    return page.extract_words(extra_attrs=["size"])


def _vertikale(page):
    return [ln for ln in page.lines if abs(ln["x1"] - ln["x0"]) < 0.6]


def _geometri(page):
    """Hour axis from the printed 0..24 labels and the tick row under them.

    Only ticks directly under the label row count: legend icons and label
    leader lines are short vertical lines too, and one of those near the
    "23" label skewed a page's scale by a percent — enough to move every
    boundary on it by ten minutes. The scale is the median tick spacing,
    so one odd tick cannot do that again; the scale itself comes from the
    widest span of ticks the median agrees with.
    """
    words = _ord(page)
    per_linje = defaultdict(list)
    for w in words:
        if w["size"] > 7 and re.fullmatch(r"\d{1,2}", w["text"]) and w["x0"] < 600:
            per_linje[round(w["top"])].append(w)
    if not per_linje:
        raise ValueError("Fant ingen timeakse på siden.")
    akse = max(per_linje.values(), key=len)
    akse_top = akse[0]["top"]
    ticks = sorted({
        round(ln["x0"], 1) for ln in _vertikale(page)
        if 3 < ln["bottom"] - ln["top"] < 6 and 5 < ln["top"] - akse_top < 20
    })
    if not ticks:
        raise ValueError("Fant ingen timestreker på siden.")
    x_for = {}
    for w in akse:
        senter = (w["x0"] + w["x1"]) / 2
        x_for[int(w["text"])] = min(ticks, key=lambda t: abs(t - senter))
    if 0 not in x_for or len(x_for) < 3:
        raise ValueError("Timeaksen mangler 0 eller er for kort.")
    timer = sorted(x_for)
    avstander = sorted((x_for[b] - x_for[a]) / (b - a) for a, b in zip(timer, timer[1:]))
    grov = avstander[len(avstander) // 2]
    # The median spacing rejects a tick that is not on the axis; the widest
    # span of the ticks that remain gives the scale to the precision needed
    # (the rounding of one tick, spread over 23 hours).
    gode = [h for h in timer if abs(x_for[h] - (x_for[0] + h * grov)) < 1.5]
    if len(gode) < 3:
        raise ValueError("Timeaksen er uleselig.")
    return Geometri(h0=x_for[0], pt_per_hour=(x_for[gode[-1]] - x_for[0]) / gode[-1])


def _tile_hash(image):
    return hashlib.md5(image["stream"].get_data()).hexdigest()


def _legende(page):
    """{tile hash: label} learned from the legend printed on the page.

    A tile image is wider than the icon it shows (the pattern repeats and is
    clipped), so the label is the first "= Name" whose "=" lies to the right
    of the tile's *start*, not of its end.
    """
    words = [w for w in _ord(page) if 55 < w["top"] < 92]
    ut = {}
    for im in page.images:
        if not (55 < im["top"] < 92):
            continue
        lik = sorted(
            (w for w in words
             if w["text"] == "=" and abs(w["top"] - im["top"]) < 5
             and 0 < w["x0"] - im["x0"] < 40),
            key=lambda w: w["x0"],
        )
        if not lik:
            continue
        e = lik[0]
        deler = []
        for w in sorted(
            (w for w in words if abs(w["top"] - e["top"]) < 5 and w["x0"] > e["x0"]),
            key=lambda w: w["x0"],
        ):
            if w["text"] == "=" or w["x0"] > e["x0"] + 90:
                break
            deler.append(w["text"])
        navn = " ".join(deler).replace("*", "").strip()
        if navn:
            ut.setdefault(_tile_hash(im), _LEGENDE_NAVN.get(navn, navn))
    return ut


def _stasjoneringssted(words):
    for i, w in enumerate(words):
        if w["text"].startswith("Stasjoneringssted") and i + 1 < len(words):
            return words[i + 1]["text"].strip(":")
    return None


def _rader(page):
    """(y0, y1) of every duty band, top to bottom."""
    band = sorted({
        (round(r["top"], 1), round(r["bottom"], 1)) for r in page.rects
        if r["x0"] < 30 and r["x1"] > 800 and 20 < r["bottom"] - r["top"] < 200
    })
    return band


# ── Left column ────────────────────────────────────────────────────────

def _linjer_fra_tegn(chars):
    """Rebuild text lines from chars: two overlapping lines interleave as words."""
    per_linje = defaultdict(list)
    for c in chars:
        per_linje[round(c["top"], 1)].append(c)
    ut = []
    for y in sorted(per_linje):
        cs = sorted(per_linje[y], key=lambda c: c["x0"])
        tekst, forrige = "", None
        for c in cs:
            if forrige is not None and c["x0"] - forrige > 1.2:
                tekst += " "
            tekst += c["text"]
            forrige = c["x1"]
        ut.append((y, tekst.strip()))
    return ut


def _slaa_sammen_linjer(linjer):
    """Join wrapped lines; a line ending in "-" was split mid-token."""
    ut = ""
    for t in linjer:
        if not ut:
            ut = t
        elif ut.endswith("-"):
            ut += t
        else:
            ut += " " + t
    return ut


def _venstre(page, y0, y1, h0):
    """(nr, kjoredager, materiell, [y of each +24t mark]) for one band."""
    chars = [c for c in page.chars if y0 <= c["top"] <= y1 and c["x0"] < h0 - 1]
    nr_l = _linjer_fra_tegn(c for c in chars if c["x0"] < _X_NR_MAX)
    dag_l = _linjer_fra_tegn(c for c in chars if _X_NR_MAX <= c["x0"] < _X_DAGER_MAX)
    mat_l = _linjer_fra_tegn(c for c in chars if c["x0"] >= _X_DAGER_MAX)

    nr = "".join(t for _, t in nr_l)
    nr = re.sub(r"\s+", "_", nr)
    pluss24 = [y for y, t in dag_l if t == "+24t"]
    dager = "".join(t for _, t in dag_l if _KJOREDAGER.match(t))
    materiell = _slaa_sammen_linjer(t for _, t in mat_l) or None
    return nr, dager, materiell, pluss24


# ── Timer columns ──────────────────────────────────────────────────────

def _timer_kolonner(words):
    """{column name: x centre} or None when the file has no Timer columns."""
    hode = [w for w in words if w["top"] < 100 and w["text"] in TIMER_KOLONNER]
    timer = sorted((w for w in words if w["top"] < 100 and w["text"] == "Timer"),
                   key=lambda w: w["x0"])
    if len(hode) != len(TIMER_KOLONNER) or len(timer) != len(TIMER_KOLONNER):
        return None
    hode.sort(key=lambda w: w["x0"])
    return {h["text"]: (t["x0"] + t["x1"]) / 2 for h, t in zip(hode, timer)}


def _beregninger(words, kolonner, y0, y1, h24):
    if kolonner is None:
        return None
    ut = {navn: None for navn in TIMER_KOLONNER}
    for w in words:
        if y0 <= w["top"] <= y1 and w["x0"] > h24 + 2:
            senter = (w["x0"] + w["x1"]) / 2
            navn = min(kolonner, key=lambda n: abs(kolonner[n] - senter))
            ut[navn] = w["text"]
    return ut


# ── Bars and sub-rows ──────────────────────────────────────────────────

def _delrader(page, y0, y1, h0):
    """Bar rows inside one band, each as (bar_y, [tiles]), top to bottom."""
    tiles = sorted(
        (im for im in page.images if y0 < im["top"] < y1 and im["x0"] >= h0 - 2),
        key=lambda im: im["top"],
    )
    rader = []
    for im in tiles:
        if rader and abs(im["top"] - rader[-1][0]) < 3:
            rader[-1][1].append(im)
        else:
            rader.append((im["top"], [im]))
    return rader


# ── Tokens ─────────────────────────────────────────────────────────────

def _tokens(chars):
    """Tokens rebuilt from chars: split on a gap, or where the size changes
    (a superscript that touches its word is still a separate token)."""
    per_linje = defaultdict(list)
    for c in chars:
        per_linje[round(c["top"], 1)].append(c)
    ut = []
    for y in sorted(per_linje):
        cs = sorted(per_linje[y], key=lambda c: c["x0"])
        akt = None
        for c in cs:
            if akt and -1.0 <= c["x0"] - akt["x1"] <= 0.3 and abs(c["size"] - akt["size"]) < 0.3 \
                    and not akt["text"].endswith("'"):
                akt["text"] += c["text"]
                akt["x1"] = c["x1"]
                akt["chars"].append(c)
            else:
                if akt:
                    ut.append(akt)
                akt = {"text": c["text"], "x0": c["x0"], "x1": c["x1"], "top": c["top"],
                       "size": c["size"], "chars": [c]}
        if akt:
            ut.append(akt)
    return _lim_superskrift(_uten_duplikater(ut))


def _uten_duplikater(tokens):
    """The same label drawn twice on the same spot counts once."""
    ut = []
    for t in tokens:
        if not any(f["text"] == t["text"] and abs(f["top"] - t["top"]) < 0.6
                   and abs(f["x0"] - t["x0"]) < 0.6 for f in ut):
            ut.append(t)
    return ut


def _lim_superskrift(tokens):
    """A superscript that follows a word on its line belongs to that word:
    "Tilsyn" + "[2106I-2111U]" is one label and is placed by the word."""
    ut = []
    for t in sorted(tokens, key=lambda t: (t["top"], t["x0"])):
        # Pushed left to fit before the page edge, a superscript can start
        # inside its own word; anything on the line it overlaps is its word.
        naboer = [f for f in ut if abs(t["top"] - f["top"]) < 1.5
                  and (-0.6 * (f["x1"] - f["x0"]) <= t["x0"] - f["x1"] < 1.5
                       or (t["size"] < _SUPERSKRIFT and t["x0"] <= f["x0"] <= t["x1"] + 1.5))
                  and (t["size"] < _SUPERSKRIFT or f["size"] < _SUPERSKRIFT)
                  and not _MINUTT.match(t["text"]) and not _MINUTT.match(f["text"])]
        if naboer:
            f = max(naboer, key=lambda f: f["x1"])
            f["text"] += t["text"]
            f["x1"] = t["x1"]
            f["chars"] = f["chars"] + t["chars"]
        else:
            ut.append(dict(t))
    return ut


def _del_sammenklistret(tok, grenser, ticks):
    """"SKIOSL" is two station labels that touch; "OSLDeling[...]" is a
    station followed by an activity label.

    The station pair is split where the parts sit on the marks the layout
    left: the right part starting on a leader tick (the surest sign, a
    pushed label), the left part ending on a boundary (a label in place),
    or the right part starting on a boundary.
    """
    m = re.match(r"^([A-ZÆØÅ]{2,5})(" + "|".join(re.escape(o) for o, _ in _NOKKELORD) + ")",
                 tok["text"])
    if m and len(tok["text"]) > len(m.group(1)):
        return _del_ved(tok, len(m.group(1)))
    if not re.fullmatch(r"[A-ZÆØÅ]{4,10}", tok["text"]):
        return [tok]
    beste, poeng = None, 0
    for i in range(2, len(tok["text"]) - 1):
        venstre_x1 = tok["chars"][i - 1]["x1"]
        hoyre_x0 = tok["chars"][i]["x0"]
        p = (2 * any(abs(hoyre_x0 - t) < 0.7 for t in ticks)
             + any(abs(venstre_x1 - g) < 0.7 for g in grenser)
             + any(abs(hoyre_x0 - g) < 0.7 for g in grenser))
        # Boundaries a few minutes apart sit one letter apart, so a wrong
        # split can collect two boundary hits by accident. Station codes are
        # three letters far more often than two or four, so two three-letter
        # parts outweigh that — but not a leader tick, which is exact.
        p += 1.1 * (i == 3) + 1.1 * (len(tok["text"]) - i == 3)
        if p > poeng:
            beste, poeng = i, p
    if beste is None:
        return [tok]
    venstre, hoyre = _del_ved(tok, beste)
    return [venstre] + _del_sammenklistret(hoyre, grenser, ticks)


def _del_ved(tok, i):
    venstre = dict(tok, text=tok["text"][:i], x1=tok["chars"][i - 1]["x1"], chars=tok["chars"][:i])
    hoyre = dict(tok, text=tok["text"][i:], x0=tok["chars"][i]["x0"], chars=tok["chars"][i:])
    return [venstre, hoyre]


def _tekst(tokens):
    return " ".join(t["text"] for t in sorted(tokens, key=lambda t: (round(t["top"]), t["x0"])))


def _nokkelord(tokens):
    for t in sorted(tokens, key=lambda t: (round(t["top"]), t["x0"])):
        for ord_, navn in _NOKKELORD:
            if ord_ in t["text"]:
                return navn
    return None


def _tognumre(tokens):
    ut = []
    for t in sorted(tokens, key=lambda t: (round(t["top"]), t["x0"])):
        for nr in _TALL_I_TEKST.findall(t["text"]):
            if nr not in ut:
                ut.append(nr)
    return ",".join(ut)


def _stasjon_i(tokens):
    for t in sorted(tokens, key=lambda t: (round(t["top"]), t["x0"])):
        if _STASJON.match(t["text"]) and not any(o in t["text"] for o, _ in _NOKKELORD):
            return t["text"]
    return None


# ── One bar row ────────────────────────────────────────────────────────

#: Activities that take the driver somewhere. Everything else happens at
#: the station the previous activity ended at.
_FLYTTER = {"Togaktivitet", "Passreise", "Gangtid", "Taxi", "Assistanse"}

#: How far below a bar its own labels reach (two station lines, minute
#: marks, the clock label at the row's foot). Anything lower belongs to the
#: next bar's stack of labels above it.
_UNDER_BAR = 27.0


class _Segment:
    def __init__(self, a, b, monster):
        self.a, self.b, self.monster = a, b, monster
        self.over, self.under, self.markor, self.stasjon = [], [], None, None


def _segmenter(bar_y, tiles, vlines, x_start, x_slutt, legende):
    grenser = {
        round(ln["x0"], 1) for ln in vlines
        if bar_y - 4 < ln["top"] < bar_y + 3 and ln["bottom"] > bar_y
    }
    grenser |= {round(x_start, 1), round(x_slutt, 1)}
    grenser = sorted(g for g in grenser if x_start - 0.5 <= g <= x_slutt + 0.5)
    ut = []
    for a, b in zip(grenser, grenser[1:]):
        if b - a < 0.3:
            continue
        tile = next((im for im in tiles if abs(im["x0"] - a) < 0.8), None)
        ut.append(_Segment(a, b, legende.get(_tile_hash(tile)) if tile else None))
    return ut


def _segment_ved_start(segs, x, tol=0.35):
    return next((s for s in segs if abs(s.a - x) < tol), None)


def _segment_ved_slutt(segs, x, tol=0.7):
    """The segment whose arrival boundary is closest to x, within tol."""
    kand = [s for s in segs if abs(s.b - x) < tol]
    return min(kand, key=lambda s: abs(s.b - x)) if kand else None


def _segment_rundt(segs, x):
    return next((s for s in segs if s.a <= x < s.b), None)


def _plasser_over(segs, tok):
    """Above the bar: left-aligned on its start boundary, else centred."""
    return _segment_ved_start(segs, tok["x0"]) or _segment_rundt(segs, (tok["x0"] + tok["x1"]) / 2)


def _plasser_under(segs, tok, ticks):
    """Below the bar: right-aligned on its arrival boundary; when pushed
    aside a tick marks that boundary and the label starts on the tick.
    The tick is checked first — a pushed label can end near some other
    boundary by accident."""
    tick = next((t for t in ticks if abs(tok["x0"] - t) < 0.7), None)
    seg = _segment_ved_slutt(segs, tick, tol=0.3) if tick is not None else None
    if seg is None:
        seg = _segment_ved_slutt(segs, tok["x1"])
    return seg or _segment_rundt(segs, (tok["x0"] + tok["x1"]) / 2)


def _overlappende(tokens):
    """Full-size tokens that overlap another on their line. Labels are pushed
    apart when they collide, so an overlap means the generator gave up and
    printed them on top of each other; the pieces spell nothing."""
    ut = []
    store = [t for t in tokens if t["size"] >= _SUPERSKRIFT and not _MINUTT.match(t["text"])]
    for a in store:
        for b in store:
            if a is not b and abs(a["top"] - b["top"]) < 1.5 \
                    and min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]) > 0.5:
                ut.append(a)
                break
    return ut


def _bar_for_token(tok, bar_ys):
    """Which bar a label belongs to: the bar just above it when it sits in
    that bar's under-region, otherwise the nearest bar below it. A clock
    label is printed at the foot of its row, however deep that is."""
    grense = 1e9 if _KLOKKE.match(tok["text"]) else _UNDER_BAR
    over = [y for y in bar_ys if 0 < tok["top"] - y <= grense]
    if over:
        return max(over)
    under = [y for y in bar_ys if y > tok["top"]]
    return min(under) if under else None


def _x_for_klokke(tekst, geo, tykke):
    """The x of a printed clock time: a bold line there if one is drawn,
    else the axis position of the time itself."""
    t, m = tekst.split(":")
    x = geo.h0 + (int(t) * 60 + int(m)) / 60 * geo.pt_per_hour
    naer = [k for k in tykke if abs(k - x) < 1.5]
    return min(naer, key=lambda k: abs(k - x)) if naer else x


def _start_slutt(tykke, klokker, geo, fortsettelse, advarsler):
    """x of the start and end of one bar, read from the clock labels printed
    at its foot. Two labels: the left one starts the bar. One label: it ends
    a continuation row (+24t), and otherwise the label's placement decides
    — a start label ends on its line, an end label begins on it. A bar with
    no end label runs to the 24-hour edge."""
    klokker = sorted(klokker, key=lambda k: k["x0"])
    xs = [_x_for_klokke(k["text"], geo, tykke) for k in klokker]
    if len(klokker) >= 2:
        return xs[0], xs[-1]
    if len(klokker) == 1:
        k, x = klokker[0], xs[0]
        if fortsettelse or abs(k["x0"] - x) < abs(k["x1"] - x):
            return geo.h0, x
        return x, geo.h24
    if not fortsettelse:
        advarsler.append("fant ikke klokkeslett for start og slutt")
    return geo.h0, geo.h24


_KORT_TALL = re.compile(r"\d{2,3}[A-Z]?")


def _klippet_ved_kanten(t, tokens, geo):
    """Whether a label is what the generator left of a longer one.

    A label that would overflow the 24-hour edge is shortened to fit ("OSL"
    -> "OS", "2275" -> "227"), and one at the 00:00 edge loses its front
    ("FIL" -> "IL", "11935" -> "1935" printed beside the whole one). Station
    codes are three letters and train numbers four or more digits, so a
    shorter token at an edge is a cut, and a token that is the tail of
    another at the same spot is too.
    """
    tekst = t["text"]
    kort_stasjon = bool(re.fullmatch(r"[A-ZÆØÅ]{2}", tekst))
    kort_tall = bool(_KORT_TALL.fullmatch(tekst))
    if kort_stasjon and t["x1"] > geo.h24 - 6:
        return True
    if kort_tall and t["x1"] > geo.h24 - 2.5:
        return True
    if t["x0"] <= geo.h0 + 0.3:
        if kort_stasjon:
            return True
        # Three-digit trains exist (334 runs past midnight and starts the
        # next row), so a number at the 00:00 edge is a cut only when the
        # whole label is printed beside it.
        if any(f is not t and abs(f["x0"] - t["x0"]) < 0.5 and abs(f["top"] - t["top"]) < 6
               and f["text"] != tekst and f["text"].endswith(tekst) for f in tokens):
            return True
    return False


def _les_bar(geo, legende, bar_y, tiles, vlines, ticks, tokens, x_start, x_slutt,
             start_stasjon, advarsler):
    """The activities of one bar, in order, with stations propagated."""
    segs = _segmenter(bar_y, tiles, vlines, x_start, x_slutt, legende)
    if not segs:
        return [], start_stasjon
    grenser = sorted({s.a for s in segs} | {s.b for s in segs})
    ankere = sorted(set(grenser) | set(ticks))
    tokens = [d for t in tokens for d in _del_sammenklistret(t, grenser, ticks)]
    slutt_stasjon = None

    for t in tokens:
        tekst = t["text"]
        if _KLOKKE.match(tekst):
            continue
        if _MINUTT.match(tekst):
            naermeste = min(ankere, key=lambda a: abs(a - t["x0"]))
            if abs(naermeste - t["x0"]) < 3 and \
                    abs(int(round(geo.minutter(naermeste))) % 60 - int(tekst[:-1])) > 1:
                advarsler.append(f"minuttmerke {tekst} ved {geo.tid(naermeste)}")
            continue
        if _klippet_ved_kanten(t, tokens, geo):
            advarsler.append(f"etikett klippet ved døgnskiftet: «{tekst}»")
            continue
        if t["x1"] <= x_start + 0.5 and _STASJON.match(tekst):
            start_stasjon = tekst
            continue
        if t["x0"] >= x_slutt - 0.5 and _STASJON.match(tekst):
            slutt_stasjon = tekst
            continue
        if t["top"] < bar_y - 1:
            seg = _plasser_over(segs, t)
            if seg:
                seg.over.append(t)
            else:
                advarsler.append(f"etikett «{tekst}» uten segment")
            continue
        if tekst in _MARKOR:
            seg = _segment_rundt(segs, (t["x0"] + t["x1"]) / 2)
            if seg:
                seg.markor = _MARKOR[tekst]
            continue
        if _STASJON.match(tekst):
            seg = _plasser_under(segs, t, ticks)
            if seg:
                seg.stasjon = tekst
            else:
                advarsler.append(f"stasjon {tekst} uten segment")
            continue
        seg = _plasser_over(segs, t)
        if seg:
            seg.under.append(t)

    ut, forrige_til = [], start_stasjon
    for s in segs:
        tokens_ = s.over + s.under
        eksplisitt = s.stasjon or _stasjon_i(s.over)
        typ = _nokkelord(tokens_) or s.markor or s.monster or "Opphold"
        ut.append({
            "fra_tid": geo.tid(s.a),
            "til_tid": geo.tid(s.b),
            "fra_stasjon": forrige_til,
            "til_stasjon": eksplisitt or forrige_til,
            "type": typ,
            "monster": s.monster,
            "tognumre": _tognumre(tokens_),
            "tekst": _tekst(tokens_),
            "_eksplisitt": bool(eksplisitt),
        })
        forrige_til = eksplisitt or forrige_til
    if slutt_stasjon and not ut[-1]["_eksplisitt"]:
        ut[-1]["til_stasjon"] = slutt_stasjon
        ut[-1]["_eksplisitt"] = True
        forrige_til = slutt_stasjon
    _fyll_inn_ankomst(ut)
    _arv_tognummer(ut)
    return ut, forrige_til


def _arv_tognummer(aktiviteter):
    """An unlabelled leg drawn straight after a labelled one is the same
    train: the number is printed once, the stops along the way are not."""
    for i in range(1, len(aktiviteter)):
        her, forrige = aktiviteter[i], aktiviteter[i - 1]
        if her["type"] == "Togaktivitet" and not her["tognumre"] \
                and forrige["type"] == "Togaktivitet" and forrige["tognumre"] \
                and forrige["til_tid"] == her["fra_tid"]:
            her["tognumre"] = forrige["tognumre"]


def _fyll_inn_ankomst(aktiviteter):
    """A stop labelled with a station says where the train before it went:
    "1590" then "Fra/Ins ... LOD" means 1590 ran to LOD."""
    for i in range(1, len(aktiviteter)):
        her, forrige = aktiviteter[i], aktiviteter[i - 1]
        if her["_eksplisitt"] and her["type"] not in _FLYTTER \
                and not forrige["_eksplisitt"] and forrige["type"] in _FLYTTER:
            forrige["til_stasjon"] = her["til_stasjon"]
            forrige["_eksplisitt"] = True
            her["fra_stasjon"] = her["til_stasjon"]
    for a in aktiviteter:
        del a["_eksplisitt"]


def _slaa_sammen_midnatt(forrige, neste):
    """A train that runs past midnight is one activity, not a 24:00 cut."""
    if forrige and neste and forrige[-1]["til_tid"] == "00:00" and neste[0]["fra_tid"] == "00:00" \
            and forrige[-1]["monster"] == neste[0]["monster"]:
        a, b = forrige[-1], neste[0]
        a["til_tid"] = b["til_tid"]
        a["til_neste_dag"] = 1
        a["til_stasjon"] = b["til_stasjon"] or a["til_stasjon"]
        for nr in b["tognumre"].split(","):
            if nr and nr not in a["tognumre"].split(","):
                a["tognumre"] = ",".join(filter(None, [a["tognumre"], nr]))
        a["tekst"] = " ".join(filter(None, [a["tekst"], b["tekst"]]))
        del neste[0]
        if neste:
            neste[0]["fra_stasjon"] = a["til_stasjon"]


# ── Assembly ───────────────────────────────────────────────────────────

def _les_dagsverk(page, geo, legende, vlines, y0, y1, pluss24):
    """One band: its bars, their labels, and the activities in order."""
    delrader = _delrader(page, y0, y1, geo.h0)
    if not delrader:
        return None
    bar_ys = [by for by, _ in delrader]
    tykke = sorted({
        round(ln["x0"], 1) for ln in vlines
        if ln["linewidth"] > 0.4 and y0 - 1 <= ln["top"] and ln["bottom"] <= y1 + 1
        and ln["x0"] >= geo.h0 - 1
    })
    ticks = sorted({
        round(o["x0"], 1) for o in list(page.lines) + list(page.curves)
        if abs(o["x1"] - o["x0"]) < 0.6 and y0 <= o["top"] <= y1
        and o["x0"] >= geo.h0 - 1
        and any(_TICK_AVSTAND[0] < o["top"] - by < _TICK_AVSTAND[1] for by in bar_ys)
    })
    chars = [c for c in page.chars
             if y0 <= c["top"] <= y1 and geo.h0 - 40 <= c["x0"] < geo.h24 + 1]
    per_bar = defaultdict(list)
    klippet = []
    alle = _tokens(chars)
    overlappende = _overlappende(alle)
    for t in alle:
        if t in overlappende:
            klippet.append(t["text"])
            continue
        if t["x0"] < geo.h0 - 0.3 and t["x1"] > geo.h0 + 0.3:
            # Started left of the axis: a label the generator cut at the
            # page edge (the left column's own text sits further left).
            klippet.append(t["text"])
            continue
        if t["x0"] < geo.h0 - 0.3:
            continue
        if t["x0"] > geo.h24 - 1.5:
            klippet.append(t["text"])
            continue
        by = _bar_for_token(t, bar_ys)
        if by is not None:
            per_bar[by].append(t)

    advarsler, aktiviteter = [], []
    for t in klippet:
        advarsler.append(f"etikett klippet ved sidekanten: «{t}»")
    start = slutt = None
    neste_dag = 0
    stasjon = None
    for i, (bar_y, tiles) in enumerate(delrader):
        tokens = per_bar[bar_y]
        # The +24t mark is printed level with its bar; on a short band it is
        # within reach of both bars, so nearest wins.
        fortsettelse = any(min(bar_ys, key=lambda b: abs(b - y)) == bar_y for y in pluss24)
        klokker = [t for t in tokens if _KLOKKE.match(t["text"]) and t["top"] > bar_y]
        bar_ticks = [x for x in ticks if any(
            _TICK_AVSTAND[0] < o["top"] - bar_y < _TICK_AVSTAND[1]
            for o in list(page.lines) + list(page.curves)
            if abs(o["x0"] - x) < 0.05 and abs(o["x1"] - o["x0"]) < 0.6)]
        x_start, x_slutt = _start_slutt(tykke, klokker, geo, fortsettelse, advarsler)
        if i == 0:
            start = geo.tid(x_start)
        slutt = geo.tid(x_slutt)
        rad, stasjon = _les_bar(geo, legende, bar_y, tiles, vlines, bar_ticks, tokens,
                                x_start, x_slutt, stasjon, advarsler)
        for a in rad:
            a["fra_neste_dag"] = a["til_neste_dag"] = 1 if fortsettelse else 0
        if fortsettelse:
            neste_dag = 1
            _slaa_sammen_midnatt(aktiviteter, rad)
        aktiviteter.extend(rad)
    for n, a in enumerate(aktiviteter, start=1):
        a["radnr"] = n
    return {
        "start": start, "slutt": slutt, "slutt_neste_dag": neste_dag,
        "advarsler": advarsler, "aktiviteter": aktiviteter,
    }


def _les_side(page, side_nr):
    words = _ord(page)
    geo = _geometri(page)
    legende = _legende(page)
    sted = _stasjoneringssted(words)
    kolonner = _timer_kolonner(words)
    vlines = _vertikale(page)
    duties, warnings = [], []

    for y0, y1 in _rader(page):
        nr, dager, materiell, pluss24 = _venstre(page, y0, y1, geo.h0)
        if not _DV_NR.match(nr):
            continue
        lest = _les_dagsverk(page, geo, legende, vlines, y0, y1, pluss24)
        if lest is None:
            warnings.append(f"{nr}: ingen strek funnet (side {side_nr}).")
            continue
        duties.append({
            "stasjoneringssted": sted,
            "nr": nr,
            "kjoredager": dager,
            "materiell": materiell,
            "side": side_nr,
            "beregninger": _beregninger(words, kolonner, y0, y1, geo.h24),
            "kommentar": None,
            **lest,
        })
    return duties, warnings


def parse_strekliste(pdf_path):
    """Every duty in the file, page by page. A page that fails is one warning."""
    res = ParseResult()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                duties, warnings = _les_side(page, i)
            except Exception as e:  # noqa: BLE001 — one bad page must not sink the file
                res.warnings.append(f"Side {i} kunne ikke leses: {e}")
                continue
            res.duties.extend(duties)
            res.warnings.extend(warnings)
    return res
