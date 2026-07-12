# UX Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize and reorganize the Turnushjelper UI: make the turnusliste scannable (compact mode + search), move view controls out of the account menu into a toolbar, add sort presets and a legend, soften the shift color palette, and fix a batch of small copy/UX bugs.

**Architecture:** All changes are frontend (Jinja templates, CSS, vanilla JS) plus one tiny Flask change (a flash message). No database or model changes, no new dependencies, no Alembic migrations. The turnusliste gets a sticky toolbar that becomes the single home for search, view options, sort presets, and the legend; the account dropdown keeps only account concerns.

**Tech Stack:** Flask + Jinja2, Bootstrap 5 (already loaded), Bootstrap Icons (`bi-*`), vanilla ES-module JS in `app/static/js/modules/`, plain-script JS in `app/static/js/modules/turnusliste.js`, CSS custom properties in `app/static/css/base/variables.css`.

## Global Constraints

- UI text is **Norwegian**; code and comments are **English** (per CLAUDE.md).
- **No inline `<style>` blocks** and no new inline `style=""` attributes — new CSS goes in shared CSS files (existing inline styles you are not asked to touch stay as they are).
- Run all Python through the project venv: `./venv/bin/python`, `./venv/bin/pytest`.
- Run the dev server with `./venv/bin/python run.py` (port 8080, debug on).
- Local dev DB is `dummy.db` (sqlite). It has user `testuser2` / password `uxtest1234` (regular user, has favorites) and `admin` / `uxtest1234` (admin). Do not modify the DB; do not run alembic.
- Playwright + chromium are already installed in the venv (verified 2026-07-12). Use them only for the verification scripts in this plan.
- Never commit `dummy.db`, screenshots, or files under `scripts/verify_*` unless the task says so.
- Every task ends with `./venv/bin/pytest -x` passing and a git commit. End commit messages with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- The full test suite is the gate: if a test unrelated to your change fails **before** you change anything, stop and report; do not fix unrelated tests.
- IDs like `#shift-size-slider`, `#favorites-toggle-btn`, `#hide-table-toggle-btn`, `#turnus-search` are wired by `app/static/js/modules/turnusliste.js` — when a task says "move" markup, the ID must move with it and exist exactly once per page.

---

### Task 1: Copy fixes — "Tordag" typo, wrong page title, label wrap, admin button color

**Files:**
- Create: `tests/test_template_content.py`
- Modify: `app/templates/turnusliste.html:6` (title block), `app/templates/turnusliste.html:427` (typo)
- Modify: `app/templates/favorites.html:158` (typo)
- Modify: `app/templates/mintur.html:82` (typo)
- Modify: `app/templates/minside.html:60` (label)
- Modify: `app/templates/admin.html:73` (button color)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_template_content.py` with a `TEMPLATES` Path constant other tasks' tests may reuse.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_template_content.py`:

```python
"""Template-level regression checks for UI copy that has no route-level test.

These read template source directly so they do not need an app context or
seeded turnus data.
"""
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


def _all_templates():
    return {p: p.read_text(encoding="utf-8") for p in TEMPLATES.rglob("*.html")}


def test_no_tordag_typo_anywhere():
    hits = [str(p) for p, text in _all_templates().items() if "Tordag" in text]
    assert hits == [], f"'Tordag' (typo for 'Torsdag') found in: {hits}"


def test_turnusliste_page_title_is_turnusliste():
    text = (TEMPLATES / "turnusliste.html").read_text(encoding="utf-8")
    assert "{% block title %}Turnusliste{% endblock %}" in text
    assert "{% block title %}Favoritter{% endblock %}" not in text


def test_minside_seniority_label_is_short():
    text = (TEMPLATES / "minside.html").read_text(encoding="utf-8")
    assert "Ansiennitetsnr.:" not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_template_content.py -v`
Expected: 3 FAILED (Tordag found in 3 templates; wrong title; long label present).

- [ ] **Step 3: Fix the templates**

1. In `app/templates/turnusliste.html`, `app/templates/favorites.html`, and `app/templates/mintur.html`: replace the single occurrence of the word `Tordag` with `Torsdag` (it is a `<th>` day header in each file).
2. In `app/templates/turnusliste.html` line 6: change `{% block title %}Favoritter{% endblock %}` to `{% block title %}Turnusliste{% endblock %}` (the turnusliste page currently shows "Favoritter" in the browser tab).
3. In `app/templates/minside.html` line 60: change

```html
<dt class="col-sm-4">Ansiennitetsnr.:</dt>
```

to

```html
<dt class="col-sm-4">Ansiennitet:</dt>
```

(the long label wraps and orphans the colon on its own line).
4. In `app/templates/admin.html` line 73: change `class="btn btn-info mt-auto"` to `class="btn btn-primary mt-auto"` so both "Administrer" buttons on the admin panel use the same primary color.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_template_content.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Run the full suite and commit**

Run: `./venv/bin/pytest -x`
Expected: all pass.

```bash
git add tests/test_template_content.py app/templates/turnusliste.html app/templates/favorites.html app/templates/mintur.html app/templates/minside.html app/templates/admin.html
git commit -m "fix: Torsdag typo, turnusliste tab title, minside label wrap, admin button color

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Flash message on silent /mintur redirect

When a user without an innplassert turnus opens `/mintur`, the route silently redirects to `/turnusliste` (no explanation). Add an info flash; `turnusliste.html` already renders flashed messages at the top of its content block.

**Files:**
- Modify: `app/routes/shifts/mintur.py:1` (import) and the redirect near line 161
- Create: `tests/test_mintur_redirect.py`

**Interfaces:**
- Consumes: `TurnusSet` model (`app/models.py`), `login_user` helper (`tests/conftest.py`).
- Produces: nothing used by later tasks.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mintur_redirect.py`:

```python
"""/mintur without an innplassering must redirect with an explanatory flash."""
from app.models import TurnusSet
from tests.conftest import login_user


def test_mintur_without_placement_redirects_with_message(client, db_session, sample_user):
    ts = TurnusSet(name="R26", year_identifier="R26", is_active=1)
    db_session.add(ts)
    db_session.commit()

    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.get("/mintur", follow_redirects=False)

    assert resp.status_code == 302
    assert "/turnusliste" in resp.headers["Location"]
    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
    assert any("innplassert" in message for _, message in flashes), flashes
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./venv/bin/pytest tests/test_mintur_redirect.py -v`
Expected: FAIL on the flash assertion (redirect happens, but `_flashes` is empty). If instead the route returns 200 or 500, stop and inspect `app/routes/shifts/mintur.py` — the test setup must match whatever condition triggers the redirect at line ~161; adjust the seed data (not the assertion) accordingly.

- [ ] **Step 3: Add the flash**

In `app/routes/shifts/mintur.py`, change line 1 from:

```python
from flask import redirect, render_template, request, url_for
```

to:

```python
from flask import flash, redirect, render_template, request, url_for
```

Then find `return redirect(url_for("shifts.turnusliste"))` (line ~161, the no-placement path) and insert directly above it, with the same indentation:

```python
        flash(
            "Du har ingen innplassert turnus ennå — du ser turnuslisten i stedet.",
            "info",
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./venv/bin/pytest tests/test_mintur_redirect.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/routes/shifts/mintur.py tests/test_mintur_redirect.py
git commit -m "feat: explain the mintur->turnusliste redirect with a flash message

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Turnusliste toolbar with name search

Add a sticky toolbar above the turnus list. In this task it only contains the search field; Tasks 5, 6 and 8 add their controls into the same bar.

**Files:**
- Create: `app/static/css/turnusliste/toolbar.css`
- Modify: `app/templates/turnusliste.html` (link CSS at line ~3; insert toolbar markup inside `{% block content %}`)
- Modify: `app/static/js/modules/turnusliste.js` (search logic)
- Create: `scripts/verify_ux_toolbar.py` (Playwright check, committed — reused by later tasks)

**Interfaces:**
- Consumes: existing DOM: `.turnus-list .list-group-item` items each containing an `.t-name` heading (see `turnusliste.html:334-341`).
- Produces: a `div.list-toolbar` element inside `#turnusliste-toolbar-row`; later tasks insert controls into `.list-toolbar` **after** the `.toolbar-search` div. Also the CSS class `.search-hidden` on filtered-out items.

- [ ] **Step 1: Create the toolbar CSS**

Create `app/static/css/turnusliste/toolbar.css`:

```css
/* ====================================
   TURNUSLISTE TOOLBAR
   Sticky bar above the list: search, view options,
   sort presets, legend toggle.
   ==================================== */

.list-toolbar {
    position: sticky;
    top: 0.5rem;
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    padding: 0.5rem 0.75rem;
    background: var(--color-bg-primary);
    border: 1px solid var(--color-bg-tertiary);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
}

.toolbar-search {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1 1 200px;
    max-width: 340px;
}

.toolbar-search .form-control {
    border-radius: var(--radius-md);
}

.toolbar-search-count {
    white-space: nowrap;
}

/* Items filtered out by the toolbar search */
.turnus-list .list-group-item.search-hidden {
    display: none;
}
```

- [ ] **Step 2: Add the markup**

In `app/templates/turnusliste.html`, add the stylesheet link next to the existing ones at the top of `{% block extra_css %}` (after line 3):

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/turnusliste/toolbar.css') }}" />
```

Then inside `{% block content %}`, in `<main class="main-content">`, insert **before** the existing "Current Sorting Display" `container-fluid` (the `#sorting-info` block at line ~311):

```html
<!-- List toolbar: search + view controls (controls added by later features) -->
<div class="container-fluid mb-2" id="turnusliste-toolbar-row">
    <div class="list-toolbar">
        <div class="toolbar-search">
            <i class="bi bi-search text-muted"></i>
            <input
                type="search"
                class="form-control form-control-sm"
                id="turnus-search"
                placeholder="Søk etter turnus …"
                autocomplete="off"
                aria-label="Søk etter turnus"
            />
            <span class="toolbar-search-count text-muted small" id="turnus-search-count"></span>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Add the search logic**

In `app/static/js/modules/turnusliste.js`, inside the existing `document.addEventListener('DOMContentLoaded', function() { ... })` handler (append before its closing `});` at the file end):

```javascript
    // Toolbar search: filter list items by turnus name
    const searchInput = document.getElementById('turnus-search');
    const searchCount = document.getElementById('turnus-search-count');

    if (searchInput) {
        const searchItems = Array.from(
            document.querySelectorAll('.turnus-list .list-group-item')
        );

        searchInput.addEventListener('input', function () {
            const query = searchInput.value.trim().toLowerCase();
            let visible = 0;

            searchItems.forEach(li => {
                const name =
                    li.querySelector('.t-name')?.textContent.trim().toLowerCase() || '';
                const match = query === '' || name.includes(query);
                li.classList.toggle('search-hidden', !match);
                if (match) visible++;
            });

            if (searchCount) {
                searchCount.textContent =
                    query === '' ? '' : `${visible} av ${searchItems.length}`;
            }
        });
    }
```

- [ ] **Step 4: Create the Playwright verification script**

Create `scripts/verify_ux_toolbar.py`:

```python
"""Verify the turnusliste toolbar search. Requires the dev server on :8080.

Usage: ./venv/bin/python scripts/verify_ux_toolbar.py
Env:   TURNUS_USER / TURNUS_PASS override the default dev login.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
USER = os.environ.get("TURNUS_USER", "testuser2")
PASS = os.environ.get("TURNUS_PASS", "uxtest1234")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(BASE + "/login")
    page.fill("input[name='username']", USER)
    page.fill("input[name='password']", PASS)
    page.click("input[type='submit'], button[type='submit']")
    page.wait_for_load_state("networkidle")

    page.goto(BASE + "/turnusliste")
    page.wait_for_load_state("networkidle")

    search = page.locator("#turnus-search")
    assert search.count() == 1, "toolbar search input missing"

    total = page.locator(".turnus-list .list-group-item").count()
    search.fill("OSL 01")
    page.wait_for_timeout(300)
    visible = page.locator(".turnus-list .list-group-item:not(.search-hidden)").count()
    assert 0 < visible < total, f"search filter broken: {visible}/{total} visible"

    search.fill("")
    page.wait_for_timeout(300)
    visible = page.locator(".turnus-list .list-group-item:not(.search-hidden)").count()
    assert visible == total, "clearing search must restore all items"

    browser.close()

print("OK: toolbar search works")
sys.exit(0)
```

Note: search matches against the *displayed* name (`.t-name` runs through the `display_name` filter, e.g. "OSL 01"), so the script searches for "OSL 01", not "OSL_01".

- [ ] **Step 5: Verify against the running app**

```bash
./venv/bin/python run.py &
SERVER_PID=$!
sleep 3
./venv/bin/python scripts/verify_ux_toolbar.py
kill $SERVER_PID
```

Expected output: `OK: toolbar search works`

- [ ] **Step 6: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/static/css/turnusliste/toolbar.css app/templates/turnusliste.html app/static/js/modules/turnusliste.js scripts/verify_ux_toolbar.py
git commit -m "feat: sticky toolbar with turnus name search on turnusliste

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Compact list by default with per-card expand

The turnusliste is ~13,500px tall because every turnus renders its full 6-week table. A global "hide tables" mode already exists (`.printable.hide-table`, toggled by `#hide-table-toggle-btn`, persisted in `localStorage['turnuslisteHideTable']`). Make it the **default for new visitors**, and add a per-card chevron that expands one card's table while compact mode is on. The same JS runs on the favorites page (it also loads `turnusliste.js` and `view-options.css`), so favorites get this for free.

**Files:**
- Modify: `app/static/js/modules/turnusliste.js` (default + chevron injection)
- Modify: `app/static/css/turnusliste/view-options.css` (expansion overrides; the hide-table block is at the end of the file, starting `/* --- Hide-table mode`)

**Interfaces:**
- Consumes: `.printable` container, `.turnus-list .list-group-item` items, `template[data-lazy-table]` lazy rendering (from `lazy-tables.js` — tables render into hidden wrappers as items scroll into view; this is fine).
- Produces: CSS class `table-expanded` on a `.list-group-item`; button class `.table-expand-btn`.

- [ ] **Step 1: Change the default and labels in turnusliste.js**

In `app/static/js/modules/turnusliste.js`, find the hide-table block (starts `const hideTableBtn = document.getElementById('hide-table-toggle-btn');`). Replace the line:

```javascript
        let hideTable = localStorage.getItem('turnuslisteHideTable') === '1';
```

with:

```javascript
        // Compact (tables hidden) is the default for first-time visitors
        const storedHideTable = localStorage.getItem('turnuslisteHideTable');
        let hideTable = storedHideTable === null ? true : storedHideTable === '1';
```

and replace the two label lines inside `updateHideTableBtn()`:

```javascript
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Vis tabell';
```

becomes

```javascript
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Vis alle tabeller';
```

and

```javascript
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Skjul tabell';
```

becomes

```javascript
                hideTableBtn.innerHTML = '<i class="bi bi-table me-1"></i>Kompakt visning';
```

- [ ] **Step 2: Inject the per-card expand chevron**

Still inside the `DOMContentLoaded` handler in `turnusliste.js`, append (before the closing `});`):

```javascript
    // Per-card expand chevron: shows one card's table while compact mode is on.
    // Injected on both turnusliste and favorites (same markup pattern).
    if (printable) {
        document.querySelectorAll('.turnus-list .list-group-item').forEach(li => {
            const header = li.querySelector(':scope > div'); // card header row
            if (!header) return;

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm btn-outline-secondary table-expand-btn ms-2';
            btn.title = 'Vis/skjul tabellen for denne turnusen';
            btn.setAttribute('aria-expanded', 'false');
            btn.innerHTML = '<i class="bi bi-chevron-down"></i>';

            btn.addEventListener('click', function () {
                const expanded = li.classList.toggle('table-expanded');
                btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
                const icon = btn.querySelector('i');
                icon.classList.toggle('bi-chevron-down', !expanded);
                icon.classList.toggle('bi-chevron-up', expanded);
            });

            header.appendChild(btn);
        });
    }
```

- [ ] **Step 3: Add the CSS overrides**

Append to `app/static/css/turnusliste/view-options.css` (after the existing `.printable.hide-table .table-scroll-wrapper { display: none; }` rule):

```css
/* Per-card expansion wins over compact mode */
.printable.hide-table .list-group-item.table-expanded .table-scroll-wrapper {
    display: block;
}

/* The 3rem lazy placeholder is meaningless while the table is hidden */
.printable.hide-table .list-group-item:not(.table-expanded) .turnus-table-placeholder {
    display: none;
}

/* The chevron only makes sense in compact mode */
.printable:not(.hide-table) .table-expand-btn {
    display: none;
}
```

- [ ] **Step 4: Verify in the browser**

```bash
./venv/bin/python run.py
```

Open `http://localhost:8080/turnusliste` in a private/incognito window (empty localStorage), log in as `testuser2` / `uxtest1234`, and check:

1. The list loads **compact**: card headers + stats rows, no 6-week tables. The whole list fits in a few screens.
2. Each card header has a chevron button; clicking it expands that card's table in place (colors applied), clicking again collapses it.
3. The account dropdown item now reads "Vis alle tabeller"; clicking it shows every table and hides the chevrons; clicking again ("Kompakt visning") returns to compact.
4. `http://localhost:8080/favorites` behaves the same way (compact + chevrons).
5. Print (Utskrift in the menu) still shows tables — print output has no `.printable` wrapper state applied (the hide-table rules are scoped under `.printable`, and print uses its own path). If tables are missing in the print preview, stop and report.

- [ ] **Step 5: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/static/js/modules/turnusliste.js app/static/css/turnusliste/view-options.css
git commit -m "feat: compact turnusliste by default with per-card table expand

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---### Task 5: Move view controls out of the account menu into the toolbar

The account dropdown currently mixes account items with view controls ("Skjul favoritter", "Skjul tabell", size/columns sliders, Utskrift, AI-generer). Give the toolbar a "Visning" dropdown that owns all view controls, and slim the account menu down to account concerns.

**Files:**
- Modify: `app/templates/turnusliste.html` (`{% block user_menu_items %}` at lines 6–21; toolbar markup from Task 3; add empty `{% block mobile_print %}`)
- Modify: `app/templates/favorites.html` (`{% block user_menu_items %}` at lines 30–32; `{% block mobile_print %}` at lines 5–11; add its own toolbar)
- Modify: `app/static/css/turnusliste/toolbar.css` (dropdown width)

**Interfaces:**
- Consumes: `components/view_options_menu.html` (unchanged — it carries `#hide-table-toggle-btn`, `#shift-size-slider`, `#shift-size-reset`, `#columns-slider`, `#columns-value`); `#favorites-toggle-btn` and `printTables()` wiring already in JS.
- Produces: a `div.toolbar-view-options` dropdown inside `.list-toolbar` on both pages. Task 8 inserts its legend button after it.

- [ ] **Step 1: Add the Visning dropdown to the turnusliste toolbar**

In `app/templates/turnusliste.html`, inside the `.list-toolbar` div created in Task 3, insert **after** the closing `</div>` of `.toolbar-search`:

```html
        <div class="dropdown toolbar-view-options">
            <button
                class="btn btn-sm btn-outline-secondary dropdown-toggle"
                type="button"
                id="view-options-btn"
                data-bs-toggle="dropdown"
                aria-expanded="false"
            >
                <i class="bi bi-sliders me-1"></i>Visning
            </button>
            <ul class="dropdown-menu">
                <li>
                    <a class="dropdown-item" href="#" id="favorites-toggle-btn" onclick="return false;">
                        <i class="bi bi-eye-slash me-1"></i>Skjul favoritter
                    </a>
                </li>
                {% include 'components/view_options_menu.html' %}
                <li><hr class="dropdown-divider" /></li>
                <li>
                    <a class="dropdown-item" href="#" onclick="printTables(); return false;">
                        <i class="bi bi-printer me-1"></i>Utskrift
                    </a>
                </li>
            </ul>
        </div>
```

- [ ] **Step 2: Slim the turnusliste account menu**

In `app/templates/turnusliste.html`, replace the whole `{% block user_menu_items %}` content (lines 6–21: the old `#favorites-toggle-btn` item, the `view_options_menu.html` include, and the mobile-only AI item) so the block is empty:

```jinja
{% block user_menu_items %}{% endblock %}
```

Then add, next to the other block overrides near the top of the file, an empty print block so Utskrift leaves the account menu (its new home is the Visning dropdown):

```jinja
{% block mobile_print %}{% endblock %}
```

The AI button stays in the navbar (`{% block navbar_icon_always %}`) — it is an action, not a view option, and it is already visible on all screen sizes.

- [ ] **Step 3: Give favorites the same toolbar**

In `app/templates/favorites.html`:

1. Add the toolbar CSS link inside `{% block extra_css %}` (next to the existing view-options.css link):

```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/turnusliste/toolbar.css') }}">
```

2. Inside `{% block content %}`, insert **before** the `<div class="container-fluid printable" ...>` element:

```html
<div class="container-fluid mb-2">
    <div class="list-toolbar">
        <div class="dropdown toolbar-view-options">
            <button
                class="btn btn-sm btn-outline-secondary dropdown-toggle"
                type="button"
                id="view-options-btn"
                data-bs-toggle="dropdown"
                aria-expanded="false"
            >
                <i class="bi bi-sliders me-1"></i>Visning
            </button>
            <ul class="dropdown-menu">
                {% include 'components/view_options_menu.html' %}
                <li><hr class="dropdown-divider" /></li>
                <li>
                    <a class="dropdown-item" href="#" onclick="printTables(); return false;">
                        <i class="bi bi-printer me-1"></i>Utskrift
                    </a>
                </li>
            </ul>
        </div>
    </div>
</div>
```

(No "Skjul favoritter" here — on the favorites page everything is a favorite.)

3. Replace `{% block user_menu_items %}` (lines 30–32) with an empty block, and replace the `{% block mobile_print %}` override (lines 5–11) with an empty block:

```jinja
{% block user_menu_items %}{% endblock %}
{% block mobile_print %}{% endblock %}
```

- [ ] **Step 4: Keep the dropdown usable**

Append to `app/static/css/turnusliste/toolbar.css`:

```css
/* View-options dropdown needs room for its sliders */
.toolbar-view-options .dropdown-menu {
    min-width: 260px;
    padding: 0.5rem 0.25rem;
}
```

- [ ] **Step 5: Verify in the browser**

Start the server, log in as `testuser2` / `uxtest1234`, and check on `http://localhost:8080/turnusliste`:

1. Toolbar shows search + "Visning". The Visning dropdown contains: Skjul favoritter, Kompakt visning/Vis alle tabeller, Størrelse slider, Ved siden av hverandre slider, Utskrift — and all of them still work (sliders keep the dropdown open while dragging).
2. The account (hamburger) dropdown now contains only: user header, Min Side, (Velg Turnusår / Last ned PDF when present), Hjelp (mobile), Admin Panel (admin only), Personvern, Logg ut.
3. Repeat on `/favorites`: Visning dropdown present and functional; account menu slim.
4. Narrow the window below 992px: toolbar and Visning dropdown remain usable on mobile width.
5. Browser console shows no JS errors on either page (a duplicated element ID from a missed removal would break the sliders).

- [ ] **Step 6: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/templates/turnusliste.html app/templates/favorites.html app/static/css/turnusliste/toolbar.css
git commit -m "refactor: move view controls from account menu to list toolbar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Sort preset chips

The 11-slider "Sorter" panel is powerful but opaque. Add one-click preset chips to the toolbar that drive the existing weighting engine. The sliders stay for advanced use.

**Files:**
- Modify: `app/static/js/modules/sorting-system.js`
- Modify: `app/templates/turnusliste.html` (chips in toolbar)
- Modify: `app/static/css/turnusliste/toolbar.css` (active chip style)

**Interfaces:**
- Consumes: `SortingSystem` methods `updateSliderValue(slider)`, `sortTurnuser()`, `saveSortingSettings()`, `resetOrder()` (all exist in `sorting-system.js`); slider DOM ids like `#helgetimer-slider`.
- Produces: `SortingSystem.PRESETS` map, `sliderIdFor(key)`, `applyPreset(name)`, `setupPresetChips()`; DOM buttons `.preset-chip[data-preset]`.

- [ ] **Step 1: Add the chips markup**

In `app/templates/turnusliste.html`, inside `.list-toolbar`, after the `.toolbar-view-options` div from Task 5:

```html
        <div class="toolbar-presets d-flex align-items-center gap-1 flex-wrap" role="group" aria-label="Hurtigsortering">
            <span class="text-muted small me-1">Sorter:</span>
            <button type="button" class="btn btn-sm btn-outline-secondary preset-chip" data-preset="minst_helg">Minst helg</button>
            <button type="button" class="btn btn-sm btn-outline-secondary preset-chip" data-preset="minst_natt">Minst natt</button>
            <button type="button" class="btn btn-sm btn-outline-secondary preset-chip" data-preset="minst_tidlig">Minst tidlig</button>
            <button type="button" class="btn btn-sm btn-outline-secondary preset-chip" data-preset="mest_fri">Mest fri</button>
        </div>
```

- [ ] **Step 2: Extract the slider-id mapping (DRY)**

In `app/static/js/modules/sorting-system.js`, add this method to the class (below `getCriteriaLabel`):

```javascript
    sliderIdFor(key) {
        return key === 'shift_cnt' ? 'shift-cnt-slider' :
               key === 'before_6' ? 'before-6-slider' :
               key === 'tidlig_6_8' ? 'tidlig-6-8-slider' :
               key === 'tidlig_8_12' ? 'tidlig-8-12-slider' :
               key === 'longest_off_streak' ? 'longest-off-slider' :
               key === 'longest_work_streak' ? 'longest-streak-slider' :
               key === 'kompdager_max' ? 'kompdager-slider' :
               `${key}-slider`;
    }
```

Then in `applySavedSettings()`, replace the inline `const sliderId = key === 'shift_cnt' ? ... : `${key}-slider`;` ternary chain with:

```javascript
            const sliderId = this.sliderIdFor(key);
```

- [ ] **Step 3: Add presets**

Add to the class (weights use the same -10..10 scale as the sliders; negative = "few is better"):

```javascript
    static PRESETS = {
        minst_helg: { helgetimer: -10 },
        minst_natt: { natt: -10 },
        minst_tidlig: { tidlig: -10, before_6: -10 },
        mest_fri: { longest_off_streak: 10 },
    };

    applyPreset(presetName) {
        const preset = SortingSystem.PRESETS[presetName];
        if (!preset) return;

        // Zero everything, then apply the preset's weights
        document.querySelectorAll('.filter-slider').forEach(slider => {
            slider.value = 0;
            this.updateSliderValue(slider);
        });

        Object.entries(preset).forEach(([key, weight]) => {
            const id = this.sliderIdFor(key);
            [document.getElementById(id), document.getElementById(id + '-mobile')]
                .forEach(slider => {
                    if (slider) {
                        slider.value = weight;
                        this.updateSliderValue(slider);
                    }
                });
        });

        this.sortTurnuser();
        this.saveSortingSettings();
    }

    setupPresetChips() {
        const chips = document.querySelectorAll('.preset-chip');
        if (!chips.length) return;

        chips.forEach(chip => {
            chip.addEventListener('click', () => {
                const wasActive = chip.classList.contains('active');
                chips.forEach(c => c.classList.remove('active'));
                if (wasActive) {
                    this.resetOrder();
                } else {
                    chip.classList.add('active');
                    this.applyPreset(chip.dataset.preset);
                }
            });
        });

        // Touching a slider by hand leaves preset mode
        document.querySelectorAll('.filter-slider').forEach(slider => {
            slider.addEventListener('input', () => {
                chips.forEach(c => c.classList.remove('active'));
            });
        });
    }
```

Call it from `initializeSorting()` — after the existing `this.setupEventListeners();` line add:

```javascript
        this.setupPresetChips();
```

- [ ] **Step 4: Style the active chip**

Append to `app/static/css/turnusliste/toolbar.css`:

```css
.preset-chip.active {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: #fff;
}
```

- [ ] **Step 5: Verify in the browser**

On `http://localhost:8080/turnusliste` (logged in):

1. Click "Minst helg": list reorders (lowest Helgetimer stats first — spot-check the `Helgetimer` value in the top card's stats row vs. the bottom card's), the chip highlights, the "Sortering aktiv" banner appears, the Sorter button badge shows 1.
2. Click "Minst tidlig": previous chip deactivates, new one activates, badge shows 2 (tidlig + before_6).
3. Click the active chip again: sorting resets, banner disappears.
4. Open the Sorter slider panel and drag any slider: the chip highlight clears (manual mode).
5. Reload the page: the last preset's ordering is restored (saved settings), though the chip highlight may be gone — that is acceptable for this task.

- [ ] **Step 6: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/static/js/modules/sorting-system.js app/templates/turnusliste.html app/static/css/turnusliste/toolbar.css
git commit -m "feat: one-click sort preset chips on turnusliste toolbar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Soften the shift color palette and fix cell text contrast

The saturated cell colors (#4ade80 green, #ff9999 pink, #af57eb purple, #4a90d9 blue) predate the soft-blue theme and fail contrast with the small dark-blue shift numbers. Switch to light tints for backgrounds plus a strong same-hue text color per shift type. Hue distinctions survive, the look calms down, and text becomes readable.

**Files:**
- Modify: `app/static/css/base/variables.css:18-25` (shift color variables)
- Modify: `app/static/css/components/shift-colors.css` (text-color pairing + gradient)

**Interfaces:**
- Consumes: cell classes applied by `shift-colors.js` (`night-early`, `morning`, `midday`, `afternoon`, `evening`, `day_off`, `h-dag`) and `.post-night-recovery` from `post-night-marker.js`; cells contain `.custom-text` (shift number) and `.time-text` (times).
- Produces: `--color-shift-*-text` variables used by Task 8's legend.

- [ ] **Step 1: Replace the palette variables**

In `app/static/css/base/variables.css`, replace the block at lines 18–25:

```css
    /* Shift Colors - Classified by start + end time (see shift-classifier.js) */
    --color-shift-night-early: #87ceeb; /* Before 06:00 - Dark blue */
    --color-shift-morning: #4a90d9; /* 06:00–07:59 - Medium blue */
    --color-shift-midday: #637abf; /* 08:00–11:59 - Light sky blue */
    --color-shift-afternoon: #ff9999; /* Kveldsvakt - Pink */
    --color-shift-evening: #af57eb; /* Nattevakt - Purple */
    --color-shift-day-off: #4ade80; /* Day off - Green */
    --color-shift-holiday: #fcd34d; /* Holiday - Gold */
```

with:

```css
    /* Shift Colors - Classified by start + end time (see shift-classifier.js).
       Soft tint for the cell background + strong same-hue text color. */
    --color-shift-night-early: #dbeefb; /* Starts before 06:00 - sky */
    --color-shift-night-early-text: #155e86;
    --color-shift-morning: #d3e3f8; /* 06:00–07:59 - blue */
    --color-shift-morning-text: #1e56b0;
    --color-shift-midday: #dcdff5; /* 08:00–11:59 - indigo */
    --color-shift-midday-text: #3f4c9e;
    --color-shift-afternoon: #fcdcdc; /* Kveldsvakt - rose */
    --color-shift-afternoon-text: #b04343;
    --color-shift-evening: #ead9fa; /* Nattevakt - purple */
    --color-shift-evening-text: #6d28a8;
    --color-shift-day-off: #d9f4e3; /* Day off - green */
    --color-shift-day-off-text: #1a7a44;
    --color-shift-holiday: #fdf0c2; /* Holiday - amber */
    --color-shift-holiday-text: #8a6d1a;
```

- [ ] **Step 2: Pair text colors with backgrounds**

In `app/static/css/components/shift-colors.css`, replace the `.post-night-recovery` rule (currently hardcodes `#af57eb`):

```css
/* Recovery day after a night shift — purple fading to day-off green */
.post-night-recovery {
    background: linear-gradient(
        to right,
        var(--color-shift-evening) 0%,
        var(--color-shift-day-off) 50%
    );
}
```

and append at the end of the file:

```css
/* ====================================
   CELL TEXT CONTRAST
   Strong same-hue color for the shift number, near-black times.
   td-scoped so these win over generic link/text rules.
   ==================================== */

td.night-early .custom-text { color: var(--color-shift-night-early-text); }
td.morning .custom-text { color: var(--color-shift-morning-text); }
td.midday .custom-text { color: var(--color-shift-midday-text); }
td.afternoon .custom-text { color: var(--color-shift-afternoon-text); }
td.evening .custom-text { color: var(--color-shift-evening-text); }
td.day_off .custom-text { color: var(--color-shift-day-off-text); }
td.h-dag .custom-text { color: var(--color-shift-holiday-text); }

td.night-early .time-text,
td.morning .time-text,
td.midday .time-text,
td.afternoon .time-text,
td.evening .time-text,
td.day_off .time-text,
td.h-dag .time-text {
    color: var(--color-text-primary);
}
```

- [ ] **Step 3: Verify in the browser**

On `http://localhost:8080/turnusliste`, expand a few cards (or switch to "Vis alle tabeller") and check:

1. Cells show soft tinted backgrounds; each shift type is still visually distinct (sky / blue / indigo / rose / purple / green / amber).
2. Shift numbers are the strong hue color; times are near-black; both clearly readable on every tint. If the shift numbers did **not** change color, another rule is winning — run `grep -rn "dagsverk-link" app/static/css/` and add `td.morning .custom-text.dagsverk-link { ... }`-style variants (same seven classes, same variables) below the rules from Step 2.
3. The bed-icon recovery cells show a gentle purple→green gradient.
4. Check `/mintur`-style pages too if reachable, plus `/favorites` and the shift timeline modal (click a shift number) — all use the same classes and must not have regressed.
5. Nothing still renders in the old saturated colors (that would mean a hardcoded hex somewhere — `grep -rn "#4ade80\|#ff9999\|#af57eb\|#4a90d9\|#87ceeb\|#637abf\|#fcd34d" app/static/css/ app/static/js/` should return no hits outside comments; fix any it finds by switching them to the variables).

- [ ] **Step 4: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/static/css/base/variables.css app/static/css/components/shift-colors.css
git commit -m "feat: soften shift color palette and fix cell text contrast

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Legend explaining colors, codes, and abbreviations

Nothing in the UI explains what the colors, `X`/`O`/`T`, the bed icon, the arrow, or `KL.timer`/`Tj.timer` mean. Add a collapsible legend opened from the toolbar.

**Files:**
- Create: `app/templates/components/shift_legend.html`
- Create: `app/static/css/components/legend.css`
- Modify: `app/templates/turnusliste.html` (toolbar button + include + CSS link)
- Modify: `app/templates/favorites.html` (same)
- Modify: `tests/test_template_content.py` (legend presence test)

**Interfaces:**
- Consumes: shift color classes from Task 7 (`morning`, `midday`, …) for the swatches; Bootstrap's collapse plugin (already loaded).
- Produces: `#shift-legend` collapse element.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_template_content.py`:

```python
def test_shift_legend_included_on_list_pages():
    legend = TEMPLATES / "components" / "shift_legend.html"
    assert legend.exists(), "components/shift_legend.html missing"
    for page in ("turnusliste.html", "favorites.html"):
        text = (TEMPLATES / page).read_text(encoding="utf-8")
        assert "components/shift_legend.html" in text, f"legend not included in {page}"
```

Run: `./venv/bin/pytest tests/test_template_content.py -v` — expected: the new test FAILS.

- [ ] **Step 2: Create the legend component**

Create `app/templates/components/shift_legend.html`:

```html
{# Legend for turnus tables: shift colors, day codes, symbols, abbreviations.
   Toggled by the "Forklaring" toolbar button (Bootstrap collapse). #}
<div class="collapse" id="shift-legend">
    <div class="legend-panel">
        <div class="legend-section">
            <h6 class="legend-heading">Vakttyper</h6>
            <ul class="legend-list">
                <li><span class="legend-swatch night-early"></span> Starter før 06:00</li>
                <li><span class="legend-swatch morning"></span> Tidligvakt (starter 06–08)</li>
                <li><span class="legend-swatch midday"></span> Dagvakt (starter 08–12)</li>
                <li><span class="legend-swatch afternoon"></span> Ettermiddags-/kveldsvakt</li>
                <li><span class="legend-swatch evening"></span> Nattevakt</li>
                <li><span class="legend-swatch day_off"></span> Fridag (X, O og T)</li>
                <li><span class="legend-swatch h-dag"></span> Helligdag (H-dag)</li>
                <li><span class="legend-swatch post-night-recovery"></span> Utsoving etter nattevakt</li>
            </ul>
        </div>
        <div class="legend-section">
            <h6 class="legend-heading">Symboler og forkortelser</h6>
            <ul class="legend-list">
                <li><i class="bi bi-arrow-right"></i> Dagsverket fortsetter over midnatt</li>
                <li><b>KL.timer</b> — klokketimer i rotasjonen</li>
                <li><b>Tj.timer</b> — tjenestetimer i rotasjonen</li>
                <li><b>Kompdager (maks)</b> — flest kompensasjonsdager på én linje</li>
            </ul>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Create the legend CSS**

Create `app/static/css/components/legend.css`:

```css
/* ====================================
   SHIFT LEGEND
   Collapsible explanation of table colors and symbols.
   ==================================== */

.legend-panel {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    background: var(--color-bg-primary);
    border: 1px solid var(--color-bg-tertiary);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
}

.legend-heading {
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.legend-list {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: var(--font-size-sm);
}

.legend-list li {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.15rem 0;
}

/* Swatches reuse the shift color classes for their backgrounds */
.legend-swatch {
    display: inline-block;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: var(--radius-sm);
    border: 1px solid rgba(0, 0, 0, 0.15);
    flex-shrink: 0;
}
```

- [ ] **Step 4: Wire it into both pages**

In `app/templates/turnusliste.html`:

1. Add to `{% block extra_css %}`:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/legend.css') }}" />
```

2. Inside `.list-toolbar`, after the `.toolbar-presets` div (Task 6), add the toggle button:

```html
        <button
            class="btn btn-sm btn-outline-secondary ms-auto"
            type="button"
            data-bs-toggle="collapse"
            data-bs-target="#shift-legend"
            aria-expanded="false"
            aria-controls="shift-legend"
        >
            <i class="bi bi-info-circle me-1"></i>Forklaring
        </button>
```

3. Directly **after** the closing `</div>` of the toolbar's `container-fluid` (`#turnusliste-toolbar-row`), add:

```html
<div class="container-fluid">
    {% include 'components/shift_legend.html' %}
</div>
```

In `app/templates/favorites.html`: same three additions — CSS link in `{% block extra_css %}`, the same button inside its `.list-toolbar` (after the Visning dropdown), and the same include right after the toolbar's `container-fluid`.

- [ ] **Step 5: Run the test, verify visually, commit**

Run: `./venv/bin/pytest tests/test_template_content.py -v` — expected: PASS.

Browser check on both pages: "Forklaring" toggles the legend open/closed; swatches show the Task 7 tints; text is Norwegian and truthful. **Copy note for the reviewer:** the one-line meanings of X/O/T and KL/Tj come from the schedule domain — flag the exact wording to the project owner for confirmation in the PR/commit description, but ship this wording now.

Run: `./venv/bin/pytest -x`

```bash
git add app/templates/components/shift_legend.html app/static/css/components/legend.css app/templates/turnusliste.html app/templates/favorites.html tests/test_template_content.py
git commit -m "feat: collapsible legend for shift colors, codes and abbreviations

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Single søknadsskjema action bar

The skjema page has two differently-styled sets of download buttons (small outline set on top, big green/red set at the bottom of the sheet). Keep one set: make the top toolbar sticky and delete the bottom duplicates.

**Files:**
- Modify: `app/templates/søknadsskjema.html` (toolbar at lines ~145–157; duplicate buttons at lines ~290–297)
- Modify: `app/static/css/forms.css` (sticky style)

**Interfaces:**
- Consumes: existing `#skjema-toolbar` markup and `skjema-form` form id.
- Produces: nothing used by later tasks.

- [ ] **Step 1: Make the top toolbar sticky and keep the helper text**

In `app/templates/søknadsskjema.html`, find the bottom duplicate block (inside the `.doc-sheet`, after the `</table>`):

```html
    <!-- Download buttons (inside doc so they're visible while scrolling) -->
    <div class="no-print mt-3 d-flex gap-2 flex-wrap align-items-center">
      <button type="submit" name="format" value="docx" class="btn btn-success">
        <i class="bi bi-download me-1"></i> Last ned utfylt søknadsskjema (.docx)
      </button>
      <button type="submit" name="format" value="pdf" class="btn btn-danger">
        <i class="bi bi-file-earmark-pdf me-1"></i> Last ned utfylt søknadsskjema (.pdf)
      </button>
      <span class="text-muted small">Klikk i Kolonne 2 og 4 for å merke celler — lagres automatisk</span>
    </div>
```

Replace the whole div with just the helper text (it is genuinely useful next to the table):

```html
    <!-- Cell-marking hint (download buttons live in the sticky toolbar) -->
    <div class="no-print mt-3">
      <span class="text-muted small">Klikk i Kolonne 2 og 4 for å merke celler — lagres automatisk</span>
    </div>
```

- [ ] **Step 2: Make the toolbar sticky**

Append to `app/static/css/forms.css`:

```css
/* Søknadsskjema action toolbar: stays visible while scrolling the sheet */
#skjema-toolbar {
    position: sticky;
    top: 0.5rem;
    z-index: 100;
}

#skjema-toolbar #skjema-download-buttons {
    background: var(--color-bg-primary);
    border: 1px solid var(--color-bg-tertiary);
    border-radius: var(--radius-full);
    box-shadow: var(--shadow-md);
    padding: 0.35rem 0.75rem;
}
```

Confirm `forms.css` is actually loaded by the skjema page (`grep -n "forms.css" app/templates/søknadsskjema.html app/templates/base.html`). If it is not, put the rules in a CSS file the page does load (check its `{% block extra_css %}`), keeping the selectors identical.

- [ ] **Step 3: Verify in the browser**

On `http://localhost:8080/soknadsskjema` (logged in): only one set of action buttons, pinned while scrolling the 71-row sheet; `.docx`/`.pdf` downloads still work (click each; a file downloads); print button opens the print dialog; the hint text sits under the table.

- [ ] **Step 4: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/templates/søknadsskjema.html app/static/css/forms.css
git commit -m "refactor: single sticky action bar on soknadsskjema

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Oversikt anchor navigation

Oversikt is a very long single column of sections with no way to jump. Add a sticky pill nav that anchors to each section.

**Files:**
- Modify: `app/templates/oversikt.html` (ids on section headers at lines ~91, 154, 209, 276, 297, 319; nav after `#highlight-strip` at line ~86)
- Modify: `app/static/css/layout/oversikt.css` (pill styles + scroll offset)

**Interfaces:**
- Consumes: existing `.section-header` divs.
- Produces: section ids `sec-fridager`, `sec-kompdager`, `sec-vakttyper`, `sec-helg`, `sec-rytme`.

- [ ] **Step 1: Add ids to the section headers**

In `app/templates/oversikt.html` add an `id` attribute to these `.section-header` divs (identified by their heading text):

| Section heading | id to add |
|---|---|
| FRIDAGER PER UKEDAG (line ~91) | `id="sec-fridager"` |
| KOMPDAGER PER LINJE (line ~154) | `id="sec-kompdager"` |
| VAKTTYPE & HELG — OVERSIKT (line ~209) | `id="sec-vakttyper"` |
| HELGEPROFIL (line ~297) | `id="sec-helg"` |
| RYTMESCORE (line ~319) | `id="sec-rytme"` |

Example — line ~91 changes from:

```html
    <div class="section-header section-fridager mb-3">
```

to:

```html
    <div class="section-header section-fridager mb-3" id="sec-fridager">
```

- [ ] **Step 2: Add the pill nav**

Directly after the `<div class="highlight-strip" id="highlight-strip"></div>` element (line ~86), insert:

```html
    <!-- Sticky section navigation -->
    <nav class="oversikt-anchor-nav" aria-label="Seksjoner">
        <a class="anchor-pill" href="#sec-fridager">Fridager</a>
        <a class="anchor-pill" href="#sec-kompdager">Kompdager</a>
        <a class="anchor-pill" href="#sec-vakttyper">Vakttyper</a>
        <a class="anchor-pill" href="#sec-helg">Helg</a>
        <a class="anchor-pill" href="#sec-rytme">Rytme</a>
    </nav>
```

- [ ] **Step 3: Style it**

Append to `app/static/css/layout/oversikt.css`:

```css
/* ====================================
   SECTION ANCHOR NAV
   ==================================== */

.oversikt-anchor-nav {
    position: sticky;
    top: 0.5rem;
    z-index: 100;
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    padding: 0.4rem 0.6rem;
    margin-bottom: 1rem;
    background: var(--color-bg-primary);
    border: 1px solid var(--color-bg-tertiary);
    border-radius: var(--radius-full);
    box-shadow: var(--shadow-sm);
    width: fit-content;
}

.anchor-pill {
    padding: 0.2rem 0.75rem;
    border-radius: var(--radius-full);
    font-size: var(--font-size-sm);
    color: var(--color-text-secondary);
    text-decoration: none;
}

.anchor-pill:hover {
    background: var(--color-bg-secondary);
    color: var(--color-primary);
}

/* Land sections below the sticky nav when jumping */
.section-header {
    scroll-margin-top: 4rem;
}
```

- [ ] **Step 4: Verify in the browser**

On `http://localhost:8080/oversikt` (logged in): the pill bar sticks near the top while scrolling; each pill jumps to its section with the header visible (not hidden under the bar); mobile width wraps the pills without horizontal page scroll.

- [ ] **Step 5: Run the suite and commit**

Run: `./venv/bin/pytest -x`

```bash
git add app/templates/oversikt.html app/static/css/layout/oversikt.css
git commit -m "feat: sticky anchor navigation on oversikt

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Final verification pass

**Files:** none created; this is a gate.

- [ ] **Step 1: Full test suite**

Run: `./venv/bin/pytest`
Expected: everything passes.

- [ ] **Step 2: Toolbar regression script**

```bash
./venv/bin/python run.py &
SERVER_PID=$!
sleep 3
./venv/bin/python scripts/verify_ux_toolbar.py
```

Expected: `OK: toolbar search works`

- [ ] **Step 3: Manual sweep (server still running)**

Log in as `testuser2` / `uxtest1234` and click through, checking against each task's verify list:

1. `/turnusliste` — compact by default, search, Visning dropdown, preset chips, Forklaring legend, per-card expand, soft colors, "Torsdag" in table headers, tab title "Turnusliste".
2. `/favorites` — toolbar, compact cards, reorder arrows usable with several cards visible at once.
3. `/soknadsskjema` — one sticky action bar, downloads work.
4. `/oversikt` — anchor pills.
5. `/minside` — "Ansiennitet:" label on one line.
6. Account dropdown on every page — only account items.
7. Mobile width (~390px) — toolbar wraps, dropdowns open, no horizontal page scroll.

```bash
kill $SERVER_PID
```

- [ ] **Step 4: Report**

Summarize per task: done/deviations. List any copy that needs the project owner's confirmation (legend wording from Task 8, flash message from Task 2).

---

## Explicitly out of scope (do not attempt)

- Drag-and-drop reordering of favorites (arrows + position input already exist; compact mode makes them usable).
- Changes to the guided-tour system.
- Backend/sorting-algorithm changes, DB schema changes, new dependencies.
- Restyling the login/register pages or emails.
