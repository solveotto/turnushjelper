# Download Dropdown Design

**Date:** 2026-04-14  
**Status:** Approved

---

## Context

The navbar user dropdown currently has a single "Lagre orginal Turnusliste (PDF)" link that hardcodes one specific PDF per turnus year. As more PDFs are added to `turnusfiler/r[year]/pdf/`, there is no way to surface them without code changes. This feature replaces the single link with a submenu that dynamically lists all PDFs present in the current year's `pdf/` directory, consistent with how "Velg Turnusår" works today.

---

## Goal

Replace the single download navbar item with a submenu that:
- Scans `app/static/turnusfiler/{year_id}/pdf/` for PDF files at request time
- Lists each PDF as a download link with a cleaned-up, title-cased display name
- Hides the submenu item entirely if the directory doesn't exist or contains no PDFs
- Only shows PDFs for the user's currently selected turnus year

---

## Architecture

### 1. Context processor (`app/__init__.py`)

Extend `inject_tour_state()` to also inject `pdf_downloads` — a list of dicts:

```python
{
    "display_name": str,  # cleaned, title-cased
    "url": str,           # Flask static URL
}
```

**Scanning logic:**
- Get `current_turnus_set` via `get_user_turnus_set()` (same helper used elsewhere)
- Construct path: `AppConfig.turnusfiler_dir / {year_id} / pdf`
- If path doesn't exist → return `[]`
- List `*.pdf` files, sort alphabetically
- For each file: strip extension → strip leading `r\d+_` prefix (regex) → title-case → build static URL

**Display name examples:**
| Filename | Display name |
|---|---|
| `r26_streker.pdf` | `Streker` |
| `Innplassering R26.pdf` | `Innplassering R26` |
| `turnuser_R26.pdf` | `Turnuser R26` |

**Static URL:** `url_for('static', filename=f'turnusfiler/{year_id}/pdf/{filename}')`

### 2. Navbar template (`app/templates/base.html`)

Replace lines 164–168 (single `<a>` download link) with a submenu block:

```html
{% if pdf_downloads %}
<li>
  <a class="dropdown-item" href="#" onclick="toggleDownloadsSubmenu(event)">
    <i class="bi bi-file-earmark-pdf"></i> Last ned PDF
    <i class="bi bi-chevron-right float-end" id="downloads-chevron"></i>
  </a>
  <ul class="dropdown-menu turnus-submenu" id="downloads-submenu" style="display: none;">
    {% for pdf in pdf_downloads %}
    <li>
      <a class="dropdown-item" href="{{ pdf.url }}" download>
        <i class="bi bi-file-earmark-pdf"></i> {{ pdf.display_name }}
      </a>
    </li>
    {% endfor %}
  </ul>
</li>
{% endif %}
```

Add `toggleDownloadsSubmenu()` JS function alongside the existing `toggleTurnusSubmenu()` — identical pattern, different element IDs.

**Unauthenticated path:** The context processor has a separate early-return for unauthenticated users. That return must also include `"pdf_downloads": []` to avoid a Jinja2 `UndefinedError` on the base template.

### 3. CSS (`app/static/css/components/navbar.css`)

No new CSS needed. The submenu reuses `.turnus-submenu` and `.turnus-submenu .dropdown-item` styles already defined.

---

## Files Changed

| File | Change |
|---|---|
| `app/__init__.py` | Extend context processor to inject `pdf_downloads` |
| `app/templates/base.html` | Replace single download link with submenu + JS toggle |
| `app/routes/downloads.py` | No changes |
| `app/static/css/components/navbar.css` | No changes |

---

## Improvements Over Current State

- Dynamic file listing — adding a new PDF to `pdf/` is immediately reflected in the UI, no code change needed
- Correct icon: `bi-file-earmark-pdf` (was `bi-file-earmark-zip`)
- Cleaned display names (title-cased, prefixes stripped)
- Graceful empty state: submenu hidden if no PDFs present

---

## Verification

1. Place a PDF in `app/static/turnusfiler/r26/pdf/` and one with an `r26_` prefix
2. Run `python run.py`, log in, open the user dropdown
3. Confirm "Last ned PDF" submenu appears with correct display names
4. Click a PDF link — confirm it downloads
5. Switch to a year with no `pdf/` directory — confirm the menu item is absent
6. Switch back — confirm it reappears
