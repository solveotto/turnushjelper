# Kompdager: compute and display compensation-day counts

## Context

Per overenskomsten §5.13.1, official holidays (1. og 17. mai, nyttårsdag, skjærtorsdag, langfredag, påskeaften, 1.+2. påskedag, Kristi himmelfartsdag, 1.+2. pinsedag, 1.+2. juledag) are fridager. When a rostered fridag in the turnus lands on one of these dates, the driver gets a **kompdag**. The app currently has no kompdag concept anywhere.

Findings from exploration:
- The turnusnøkkel view (`app/routes/shifts/turnusnokkel.py`) shows holidays as **red dates**, but the red comes from manual font coloring in `turnusnøkkel_{YEAR}_org.xlsx` and is **incomplete**: påskeaften, holidays falling on Sundays (1. påskedag, 1. pinsedag) and 25.–26. des 2026 (R26) are not red. All red dates *are* official holidays (no false positives), so the red set is a strict subset.
- The schedule JSON has no calendar dates — only an abstract 6-week rotation. Calendar mapping lives solely in the Excel nøkkel (6 groups × 7 day-rows, date columns H–P). For group `g`, linje-column `j` shows rotation week `((g + j - 1) % 6) + 1`.
- **The kompdag count differs per linje** within one turnus (verified for R26, e.g. OSL_01 → linje 1..6 = [10, 3, 9, 4, 8, 5]), because linje determines which rotation week hits which calendar week.
- Off-days in the schedule are coded `X`, `O`, `T`, or empty (single-element `tid`).

User decisions:
- **Main display**: turnusnøkkel view — kompdag count **per linje**, next to the existing linjeprioritering buttons where you pick linje order.
- **Turnusliste / favorites stats grid**: show the **max** count and which linje has it (e.g. `10 (L1)`).
- **Min Turnus**: exact count for the user's own linjenummer.

Assumptions (flagged, easy to change):
1. ~~All off-day types (X, O, T, empty) generate a kompdag.~~ **Confirmed by user after implementation:** X, O and T all generate kompdager, but blank/empty days that come before or after a night shift (any shift crossing midnight) do not — they are part of the night-shift span. Verified: all 189 blank days in R26 follow a midnight-crossing shift.
2. **Also confirmed by user:** holidays after 12. desember of the rutetermin's final calendar year do not count for that termin (they belong to the next rutetermin). For R26 this excludes 25.–26. des 2026; jul 2025 still counts since R26 started 15. des 2025.
3. **Also confirmed by user:** holidays falling on a Sunday never generate a kompdag, including 17. mai (a Sunday in 2026). Hence 1. påskedag and 1. pinsedag never trigger in any year. Under the full rule set OSL_01 = [4, 1, 3, 2, 2, 4], not the originally verified [10, 3, 9, 4, 8, 5]. The red date marking still shows all holidays — only the count applies the exclusions.
2. **Holiday dates are computed** from the calendar dates in the nøkkel using §5.13.1 rules (fixed dates + Easter algorithm), not read from red font — red font is verifiably incomplete. The date *marking* in turnusnøkkel/mintur is also switched to the computed set so the display matches the count.

## Implementation

### Why holiday dates are computed, not fetched or read from the Excel

Norwegian holiday dates are fully deterministic: fixed dates (1. jan, 1. mai, 17. mai, 25.–26. des) plus Easter-derived offsets (skjærtorsdag = påske − 3, langfredag − 2, påskeaften − 1, 2. påskedag + 1, Kristi himmelfart + 39, 1./2. pinsedag + 49/50). Easter Sunday is computed with the standard Anonymous Gregorian algorithm — exact for all Gregorian years, so future years (R27, R28, …) need no data updates.

Rejected alternatives:
- **External holiday API/database** — adds a network dependency and failure mode, includes non-§5.13.1 days, and does NOT include påskeaften (a §5.13.1 fridag but not a Norwegian public holiday).
- **Red font in the Excel** — verified incomplete (see Context); usable only as a cross-check.

Validation already performed against the real files: for both R25 and R26, every red date in the Excel is in the computed set (zero false positives), and the computed set additionally contains the holidays the Excel author forgot to color (påskeaften, 1. påskedag, 1. pinsedag; plus 25.–26. des 2026 in R26). Computed 2026 dates spot-checked: skjærtorsdag 2/4, langfredag 3/4, påske 5–6/4, Kristi himmelfart 14/5, pinse 24–25/5.

**A turnus year spans two calendar years.** The nøkkel date ranges are R25: 2024-12-09 → 2025-12-14 and R26: 2025-12-15 → 2026-12-27, so R26 contains 25.–26. des **2025** and 1. jan 2026 in addition to the 2026 holidays — 15 holiday dates in total, not 13. Holidays must therefore be unioned across all years present in the scanned dates (`{d.year for d in all_dates}`), and the same union must be used for the red date marking. Verified impact: with single-year (2026-only) holidays, OSL_01 would wrongly count [9, 2, 8, 4, 7, 4]; the correct multi-year counts are [10, 3, 9, 4, 8, 5].

### 1. New module `app/utils/kompdag_utils.py`

- `_easter(year) -> date` — Anonymous Gregorian algorithm (pure Python, no new deps).
- `get_official_holidays(year) -> set[date]` — the 13 §5.13.1 days for one calendar year.
- `get_holidays_for_dates(dates) -> set[date]` — unions `get_official_holidays(y)` for every calendar year present in the given dates (`{d.year for d in dates}`), then intersects with the dates. This is the set used both for counting and for the red date marking, so the two-calendar-year span of a turnus year is always covered.
- `get_holiday_positions(year_identifier) -> list[tuple[int, int, date]] | None` — open `turnusnøkkel_{YEAR}_org.xlsx` (same path/parse as `turnusnokkel.py:57-68`), scan the date cells of all 6 groups × 7 day-rows, return `(group g, day d, date)` for each scanned date in `get_holidays_for_dates(...)`. **Dedupe by date, keeping the first occurrence in group-scan order** (matches the ical exporter's `emitted_uids` behavior; neither R25 nor R26 currently contains duplicates, this is a guard). Returns `None` if the template file is missing — callers must distinguish "no data" from "zero kompdager".
- `KOMPDAG_OFF_CODES = {"X", "O", "T", ""}` — assumption #1.
- `count_kompdager(turnus_set_id) -> dict[str, list[int]] | None` — `None` when positions are unavailable (missing Excel). Otherwise, for every turnus in the set: for linje `j` in 1..6, count holiday positions where rotation week `((g + j - 1) % 6) + 1`, day `d+1` is an off-day. Off-day condition (this is the counting core, be precise): `day dict missing` **or** (`len(tid) < 2` **and** `(tid[0] if tid else "") in KOMPDAG_OFF_CODES`). A day with two `tid` entries is a work day and never counts. Uses `DataframeManager(turnus_set_id).turnus_data` for the schedule. Cache result with flask-caching key `kompdager_{turnus_set_id}` (long TTL, e.g. 3600s — data is static per set).

For testability, put the counting core in a helper that takes `(turnus_data, positions)` directly so tests don't need DB/Excel.

### 2. Turnusnøkkel view (main display)

`app/routes/shifts/turnusnokkel.py`:
- Replace the red-font check (lines 86-91) with membership in the **multi-year** holiday set from `get_holidays_for_dates(...)` over the scanned dates.
- Compute per-turnus counts: `komp = count_kompdager(turnus_set_id)`; `kompdager = komp.get(turnus_name) if komp else None`; pass to the template.

`app/templates/turnusnokkel_print.html`:
- Show the count on each linje button in the linjeprioritering panel (lines 207-212), e.g. `Linje 1 <span class="linje-komp-badge">10</span>`, plus a short label line in the panel ("Kompdager per linje") so the number is self-explanatory. Keep the buttons' click/selection JS untouched (badge inside the button; `e.target.closest('.linje-btn[data-linje]')` already handles inner elements).
- When `kompdager` is `None` (Excel missing), render **no badges** — do not show misleading zeros. Guard with `{% if kompdager %}`.
- Add "kompdag" mention to the holiday legend text.

### 3. Turnusliste + favorites stats

`app/routes/shifts/turnusliste.py` (line 52) and `app/routes/shifts/favorites.py` (line 41): in both routes the records are currently built **inline** in the `render_template(...)` call (`df=user_df_manager.df.to_dict(orient="records")`), so first extract them to a local variable, then merge in per-turnus values:
```python
df_records = user_df_manager.df.to_dict(orient="records")
komp = count_kompdager(turnus_set_id) or {}
for row in df_records:
    counts = komp.get(row["turnus"])
    row["kompdager_max"] = f"{max(counts)} (L{counts.index(max(counts)) + 1})" if counts else "–"
```

Templates `app/templates/turnusliste.html` (stats grid, lines 527-562) and `app/templates/favorites.html` (lines 205-226): add one pair following the existing pattern:
```jinja
<span class="text-muted text-nowrap">Kompdager (maks)</span><b>{{ row.kompdager_max }}</b>
```
The grid is `repeat(8, auto)`, pairs reflow automatically — no layout change needed.

### 4. Min Turnus

`app/routes/shifts/mintur.py`:
- In `_load_mintur_data`, switch the `holiday` flag (lines 97-102) to the computed multi-year holiday set (same as turnusnøkkel).
- In `mintur()`: guard both lookups — `komp = count_kompdager(turnus_set_id)`; `counts = komp.get(shift_title) if komp else None`; `kompdager = counts[linjenummer - 1] if counts else None`; pass to the template.

`app/templates/mintur.html` (stats grid, lines 190-241): add pair `Kompdager` → exact count for the user's linje; show `–` when `kompdager` is `None`.

### 5. Tests — `tests/test_kompdag_utils.py`

- `get_official_holidays`: assert known dates for 2025/2026 (easter 2026 = 5. april, so skjærtorsdag 2. april, Kristi himmelfart 14. mai, pinse 24.–25. mai, etc.).
- `get_holidays_for_dates`: dates spanning des 2025–des 2026 must include both 25. des 2025 and 25. des 2026 (the multi-year union).
- Counting core: synthetic 6-week turnus + synthetic holiday positions → expected per-linje counts, including that a work day on a holiday gives no kompdag and off-codes in `KOMPDAG_OFF_CODES` do.
- No test depends on the Excel file or DB (helper takes data directly).

## Verification

1. `pytest` — full suite green including new tests.
2. Run `python run.py`, then check with real data (R26 active set):
   - `/turnusnokkel/<set_id>/OSL_01`: linje buttons show badges `10, 3, 9, 4, 8, 5` (verified multi-year values, including jul 2025); påskeaften 04.04.26, 1. påskedag 05.04.26 and 25.–26. des 2025/2026 all render red.
   - `/turnusliste` and `/favorites`: stats grid shows `Kompdager (maks): 10 (L1)` for OSL_01.
   - `/mintur`: exact count matching the logged-in user's linjenummer.
3. Cross-check one count by hand against the nøkkel dates + rotation.

## Open assumptions to confirm with user (noted in plan, adjustable after)

- All off-codes (X/O/T/empty) count as kompdag-generating fridager (`KOMPDAG_OFF_CODES` constant).
- Red-font marking replaced by computed §5.13.1 set in turnusnøkkel + Min Turnus date display.
