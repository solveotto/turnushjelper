"""Cross-source comparison and dagsverk enrichment for turnus data.

Both functions take turnus data in the shared JSON structure (list of
single-key dicts) regardless of producer: the timeskjema parser emits int
week/day keys, JSON loaded from disk has string keys — both are tolerated,
mirroring ``scraper_validator._get``.

``diff_turnus_data`` never judges which side is right: two sources can be
different legitimate revisions (proven for R26), so the result is rendered for
admin adjudication instead of gating the import.

``enrich_dagsverk`` copies the PDF's fuller dagsverk strings (``3006_SKNO``)
onto cells whose numeric prefix matches. It is display-only by construction —
every consumer of ``dagsverk`` extracts the numeric prefix — and safe to re-run
against an outdated PDF: a non-matching base number never enriches. Turnuser
pair by name, falling back to the tur number (``turnus_key``) when a name was
corrected in one source only (R27: ``OSL_17_ALTSOM`` fixed to ``_ALSTOM`` in
the Timeskjema, still misspelled in the PDF).
"""

import copy
import re

_BASE_NR = re.compile(r"^(\d+)")

# Same title shapes as innplassering_scraper._build_shift_lookup, which already
# resolves innplassering rows by tur number.
_KEY_PATTERNS = (
    ("Tur", re.compile(r"^OSL_(\d+)(?:_|$)")),
    ("Ramme", re.compile(r"^OSL_Ramme_(\d+)")),
    ("Utland", re.compile(r"^OSL_Utland_(\d+)")),
)


def turnus_key(title):
    """'OSL_17_ALTSOM' -> 'Tur:17', 'OSL_Ramme_01' -> 'Ramme:1'; None for any
    other shape. Identifies a turnus independently of its name suffix."""
    for kind, pattern in _KEY_PATTERNS:
        m = pattern.match(title or "")
        if m:
            return f"{kind}:{int(m.group(1))}"
    return None


def unique_keys(titles):
    """{turnus_key: title} for keys carried by exactly one of ``titles``.
    An ambiguous number must never pair two turnuser."""
    by_key = {}
    for title in titles:
        key = turnus_key(title)
        if key:
            by_key.setdefault(key, []).append(title)
    return {key: names[0] for key, names in by_key.items() if len(names) == 1}


def _as_map(data):
    return {name: turnus for entry in data for name, turnus in entry.items()}


def _get(d, key):
    """Week/day lookup tolerating int (parser/scraper) and str (JSON) keys."""
    return d.get(key, d.get(str(key)))


def _base_nr(dagsverk):
    m = _BASE_NR.match(dagsverk or "")
    return m.group(1) if m else ""


def diff_turnus_data(primary, secondary):
    """Structured, JSON-serializable diff between two turnus datasets.

    ``primary`` is the dataset being imported (timeskjema), ``secondary`` the
    verification source (PDF scrape). Dagsverk values are compared on numeric
    prefix only, so PDF suffix annotations are not differences.
    """
    primary_map = _as_map(primary)
    secondary_map = _as_map(secondary)

    diff = {
        "only_primary": sorted(set(primary_map) - set(secondary_map)),
        "only_secondary": sorted(set(secondary_map) - set(primary_map)),
        "cells": [],
        "totals": [],
    }

    for name in sorted(set(primary_map) & set(secondary_map)):
        p_turnus, s_turnus = primary_map[name], secondary_map[name]
        for uke in range(1, 7):
            p_week, s_week = _get(p_turnus, uke), _get(s_turnus, uke)
            if not isinstance(p_week, dict) or not isinstance(s_week, dict):
                continue
            for dag in range(1, 8):
                p_day, s_day = _get(p_week, dag), _get(s_week, dag)
                if not isinstance(p_day, dict) or not isinstance(s_day, dict):
                    continue
                tid_differs = p_day.get("tid") != s_day.get("tid")
                dagsverk_differs = _base_nr(p_day.get("dagsverk")) != _base_nr(
                    s_day.get("dagsverk")
                )
                if tid_differs or dagsverk_differs:
                    diff["cells"].append(
                        {
                            "turnus": name,
                            "uke": uke,
                            "dag": dag,
                            "ukedag": p_day.get("ukedag", ""),
                            "primary_tid": p_day.get("tid"),
                            "secondary_tid": s_day.get("tid"),
                            "primary_dagsverk": p_day.get("dagsverk", ""),
                            "secondary_dagsverk": s_day.get("dagsverk", ""),
                        }
                    )
        if p_turnus.get("kl_timer") != s_turnus.get("kl_timer") or p_turnus.get(
            "tj_timer"
        ) != s_turnus.get("tj_timer"):
            diff["totals"].append(
                {
                    "turnus": name,
                    "primary_kl_timer": p_turnus.get("kl_timer"),
                    "secondary_kl_timer": s_turnus.get("kl_timer"),
                    "primary_tj_timer": p_turnus.get("tj_timer"),
                    "secondary_tj_timer": s_turnus.get("tj_timer"),
                }
            )

    diff["is_empty"] = not (
        diff["only_primary"] or diff["only_secondary"] or diff["cells"] or diff["totals"]
    )
    return diff


def enrich_dagsverk(primary, secondary):
    """Return a deep copy of ``primary`` where each day-cell whose dagsverk
    numeric prefix matches the ``secondary`` (PDF) cell adopts the PDF's full
    string. Turnuser pair by name, else by a tur number unique on both sides.
    Non-matching cells, fridager/blanks, and turnuser missing from the PDF keep
    the primary value. Inputs are not mutated."""
    enriched = copy.deepcopy(primary)
    secondary_map = _as_map(secondary)
    primary_by_key = unique_keys(name for entry in primary for name in entry)
    secondary_by_key = unique_keys(secondary_map)

    for entry in enriched:
        for name, turnus in entry.items():
            s_turnus = secondary_map.get(name)
            if s_turnus is None:
                key = turnus_key(name)
                if key and primary_by_key.get(key) == name and key in secondary_by_key:
                    s_turnus = secondary_map[secondary_by_key[key]]
            if s_turnus is None:
                continue
            for uke in range(1, 7):
                p_week, s_week = _get(turnus, uke), _get(s_turnus, uke)
                if not isinstance(p_week, dict) or not isinstance(s_week, dict):
                    continue
                for dag in range(1, 8):
                    p_day, s_day = _get(p_week, dag), _get(s_week, dag)
                    if not isinstance(p_day, dict) or not isinstance(s_day, dict):
                        continue
                    base = _base_nr(p_day.get("dagsverk"))
                    if base and base == _base_nr(s_day.get("dagsverk")):
                        p_day["dagsverk"] = s_day["dagsverk"]
    return enriched
