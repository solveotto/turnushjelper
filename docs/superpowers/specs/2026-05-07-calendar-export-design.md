# Calendar Export — Design Spec

**Date:** 2026-05-07

## Context

Users receive their turnus assignment once a year. They want to import the full year's shift schedule into Google Calendar or Outlook so they can see their working days alongside other personal events. The min tur page already displays this data (dates + times from the turnusnøkkel Excel file), so all required data is in place.

The main constraint: the export must be safe — it must not be able to touch or delete any existing calendar entries.

---

## Definitions

**`year_identifier`**: the `year_identifier` field from the active turnus set record (e.g. `"R26"`). Used as-is in calendar names, file names, and UI strings. Sourced from `active_set["year_identifier"]` — the same value already used in `mintur()` to locate the Excel template file.

---

## Approach

**Downloadable .ics file** with guided import into a **dedicated new calendar** (e.g. "Turnusplan R26"). This is safe by construction: the user imports into a calendar they create just for this purpose. To undo, they delete that calendar. Their main calendar is never touched.

Re-importing the same file (same UIDs) updates rather than duplicates events in Google Calendar and Outlook — UIDs are idempotent. This reinforces the safety story and means users can safely re-export if their turnus changes.

---

## Architecture

### Shared helper
Extract `_load_mintur_data(user_id: int) -> dict | None` from `mintur()` into a private helper in `app/routes/shifts.py`. Both `mintur()` and `export_ical()` call this helper. Do **not** copy-paste the data-loading logic.

Returns a dict with keys: `shift_title`, `linjenummer`, `year_identifier`, `turnus_set_id`, `groups` (same structure as `mintur()` builds), `template_found`. Returns `None` if the user has no innplassering or no active turnus set.

### New route
`GET /mintur/export_ical` in `app/routes/shifts.py`

Query params:
- `mode` — `"auto"` (shift-type labels) or `"fixed"` (single label)
- `label` — prefix string (for `auto`) or full label string (for `fixed`)

Flow:
1. Call `_load_mintur_data(current_user.get_id())`
2. If `None` or `not template_found` → return `{"error": "Ingen turnusdata funnet"}` with HTTP 404
3. Build .ics content
4. Return `Response` with:
   - `Content-Type: text/calendar; charset=utf-8`
   - `Content-Disposition: attachment; filename="turnusplan_{year_identifier.lower()}.ics"`

### New dependency
`icalendar` — pure-Python iCalendar library, MIT licensed. Add to `requirements.txt`.

---

## iCalendar Event Structure

One `VEVENT` per working day. Days off (empty `tid`) are skipped.

| Field | Value |
|-------|-------|
| `SUMMARY` | See "Event naming" below |
| `DTSTART` | Actual date + start time, `TZID=Europe/Oslo` |
| `DTEND` | Actual date + end time, `TZID=Europe/Oslo`. Overnight shifts: end date = next day. |
| `UID` | `{shift_title}-{YYYYMMDD}@turnushjelper` |
| `DTSTAMP` | Generated automatically by `icalendar` library |
| `COLOR` | CSS hex color per shift type (silent — not documented in UI). Support varies by calendar app. |

Calendar-level properties:
- `PRODID`: `-//Turnushjelper//NO`
- `X-WR-CALNAME`: `Turnusplan {year_identifier}`
- `X-WR-TIMEZONE`: `Europe/Oslo`

Shift type → color mapping (RFC 7986 `COLOR` property, hex values approximating Google Calendar named colors):

| Shift type | Color name | Hex |
|------------|------------|-----|
| Tidlig | Påfugl (Peacock) | `#4986E7` |
| Dag | Salvia (Sage) | `#33B679` |
| Ettermiddag | Mandarín (Tangerine) | `#F6BF26` |
| Natt | Grafitt (Graphite) | `#616161` |

Only applied in `auto` mode. In `fixed` mode no `COLOR` property is set.

---

## Event Naming

Two modes, user selects in the modal before downloading:

### Mode 1 — Fixed text
Same label for every event. Text input, default `"Jobb"`.

### Mode 2 — Auto shift type
Prefix field (default `"Vy"`) + auto-detected shift type appended.

**Intentional simplification:** this uses a 4-label system that differs from the 5-class color system in `shift-classifier.js`. The color system distinguishes "before 06:00" and "06:00–07:59" separately; here both are `Tidlig` since users chose to treat all early shifts the same for calendar labelling purposes.

| Condition | Label |
|-----------|-------|
| Start before 08:00 | `Tidlig` |
| Start 08:00–11:59 | `Dag` |
| Start 12:00+, ends before 04:00 (same/next day) | `Ettermiddag` |
| Crosses midnight AND ends 04:00+ next day | `Natt` |

Result format: `"{prefix}: {type}"` — e.g. `"Vy: Tidlig"`, `"Vy: Natt"`.

---

## UI

### Button on min tur page
Add "Eksporter til kalender" button in two places in `mintur.html`, both only when `template_found` is true:
- In the `mobile_print` block (alongside "Skriv ut turnusnøkkel")
- In the main content header area (desktop visible)

### Export modal
Bootstrap modal. Contents:

1. **Step 1 — Create a dedicated calendar**
   - Instruction text: "Opprett en ny kalender kalt `Turnusplan {year_identifier}` i Google Calendar eller Outlook før du importerer."
   - Undo note: "For å angre: slett hele `Turnusplan {year_identifier}`-kalenderen. Dette påvirker ikke andre kalendere."

2. **Step 2 — Choose event title**
   - Radio toggle: "Fast tekst" / "Automatisk skifttype"
   - **Fast tekst**: text input, placeholder/default `"Jobb"`
   - **Automatisk**: prefix text input, placeholder/default `"Vy"` → live preview showing `"Vy: Tidlig"`, `"Vy: Natt"` updating as user types

3. **Step 3 — Download**
   - "Last ned .ics-fil" button → `GET /mintur/export_ical?mode=...&label=...`

4. **Step 4 — Import instructions** (collapsible)
   - Google Calendar: Innstillinger → Importer → velg fil → velg `Turnusplan {year_identifier}`
   - Outlook: Fil → Åpne og eksporter → Importer/eksporter → iCalendar-fil

### JS for modal interactivity
Inline `<script>` block within the modal in `mintur.html` (not a separate module — logic is small and modal-scoped):
- Toggle visibility of the two input fields based on radio selection
- Live-update the preview label as prefix is typed

---

## Error Handling

| Situation | Server response |
|-----------|----------------|
| User has no innplassering | HTTP 404, JSON `{"error": "Ingen turnusdata funnet"}` |
| Excel template file missing | HTTP 404, JSON `{"error": "Ingen turnusdata funnet"}` |
| Missing/invalid query params | Default to `mode="fixed"`, `label="Jobb"` |

The button is only shown when `template_found` is true, so the Excel-missing error path is a safety net for direct URL access only.

---

## Undo / Safety

- The app only generates a file — it never connects to any calendar service.
- No OAuth, no API keys, no write access to user's calendar.
- Undo = delete the dedicated calendar. Documented in the modal.
- Re-import is safe: UIDs are stable per shift+date, so re-importing updates rather than duplicates events.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/routes/shifts.py` | Extract `_load_mintur_data()` helper; add `export_ical` route (~100 lines total) |
| `app/templates/mintur.html` | Add button (×2) + modal + inline `<script>` for modal interactivity |
| `requirements.txt` | Add `icalendar` |

---

## Verification

1. `python run.py`, log in as a user with an active innplassering
2. Navigate to `/mintur` — "Eksporter til kalender" button visible (only when turnusnøkkel exists)
3. Open modal — radio toggle shows/hides correct inputs; typing in prefix field updates live preview
4. Download "Fast tekst" (`label=Jobb`) → open `.ics` in text editor: `SUMMARY:Jobb`, correct `DTSTART`/`DTEND`, `PRODID:-//Turnushjelper//NO`
5. Download "Automatisk" (`label=Vy`) → summaries are `Vy: Tidlig`, `Vy: Dag`, `Vy: Ettermiddag`, or `Vy: Natt` matching actual shift times
6. Overnight shift present → `DTEND` date is one day after `DTSTART` date
7. Days off absent from file
8. Re-import same file → no duplicate events
9. Import into Google Calendar → events appear in correct calendar at correct times
10. Direct `GET /mintur/export_ical` with no innplassering → HTTP 404 JSON response
