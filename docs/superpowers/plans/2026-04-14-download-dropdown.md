# Download Dropdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single "Lagre orginal Turnusliste (PDF)" navbar link with a submenu that dynamically lists all PDFs from the current year's `turnusfiler/{year_id}/pdf/` directory.

**Architecture:** A pure helper function scans the filesystem and returns `(filename, display_name)` pairs; the context processor in `app/__init__.py` calls it, builds Flask static URLs, and injects `pdf_downloads` into every template. `base.html` replaces the single link with a submenu that mirrors the existing "Velg Turnusår" pattern.

**Tech Stack:** Python `os`, `re`, Flask `url_for`, Jinja2, Bootstrap 5 navbar CSS (`.turnus-submenu` reused), vanilla JS toggle.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/utils/pdf_downloads.py` | Create | Pure helper — scans `pdf/` dir, returns display names |
| `tests/test_pdf_downloads.py` | Create | Unit tests for the helper |
| `app/__init__.py` | Modify | Extend context processor to inject `pdf_downloads` |
| `app/templates/base.html` | Modify | Replace single link with submenu + add JS toggle |

---

## Task 1: PDF download helper

**Files:**
- Create: `app/utils/pdf_downloads.py`
- Create: `tests/test_pdf_downloads.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pdf_downloads.py`:

```python
import os
import pytest


def test_returns_empty_when_dir_missing(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert result == []


def test_returns_empty_when_pdf_subdir_missing(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    year_dir = tmp_path / "r26"
    year_dir.mkdir()
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert result == []


def test_strips_year_prefix_and_title_cases(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    pdf_dir = tmp_path / "r26" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "r26_streker.pdf").touch()
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert len(result) == 1
    assert result[0]["filename"] == "r26_streker.pdf"
    assert result[0]["display_name"] == "Streker"


def test_title_cases_without_year_prefix(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    pdf_dir = tmp_path / "r26" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "Innplassering R26.pdf").touch()
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert result[0]["display_name"] == "Innplassering R26"


def test_ignores_non_pdf_files(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    pdf_dir = tmp_path / "r26" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "readme.txt").touch()
    (pdf_dir / "schedule.pdf").touch()
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert len(result) == 1
    assert result[0]["filename"] == "schedule.pdf"


def test_returns_sorted_alphabetically(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    pdf_dir = tmp_path / "r26" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "z_last.pdf").touch()
    (pdf_dir / "a_first.pdf").touch()
    result = get_pdf_downloads(str(tmp_path), "r26")
    assert result[0]["filename"] == "a_first.pdf"
    assert result[1]["filename"] == "z_last.pdf"


def test_accepts_uppercase_year_id(tmp_path):
    from app.utils.pdf_downloads import get_pdf_downloads
    pdf_dir = tmp_path / "r26" / "pdf"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "R26_turnusliste.pdf").touch()
    # Uppercase year_id should still resolve to lowercase dir
    result = get_pdf_downloads(str(tmp_path), "R26")
    assert len(result) == 1
    assert result[0]["display_name"] == "Turnusliste"
```

- [ ] **Step 2: Run tests — expect ImportError / FAIL**

```bash
pytest tests/test_pdf_downloads.py -v
```

Expected: `ImportError: cannot import name 'get_pdf_downloads'`

- [ ] **Step 3: Implement the helper**

Create `app/utils/pdf_downloads.py`:

```python
import os
import re


def get_pdf_downloads(base_dir: str, year_id: str) -> list[dict]:
    """Return sorted list of {filename, display_name} for PDFs in base_dir/{year_id}/pdf/.

    display_name: filename with extension stripped, leading r\\d+_ prefix removed,
    then title-cased. E.g. "r26_streker.pdf" -> "Streker".
    """
    pdf_dir = os.path.join(base_dir, year_id.lower(), "pdf")
    if not os.path.isdir(pdf_dir):
        return []
    results = []
    for filename in sorted(os.listdir(pdf_dir)):
        if not filename.lower().endswith(".pdf"):
            continue
        name = os.path.splitext(filename)[0]
        name = re.sub(r"^[Rr]\d+_", "", name)
        results.append({"filename": filename, "display_name": name.title()})
    return results
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
pytest tests/test_pdf_downloads.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/utils/pdf_downloads.py tests/test_pdf_downloads.py
git commit -m "feat: add pdf_downloads helper for navbar download submenu"
```

---

## Task 2: Extend context processor

**Files:**
- Modify: `app/__init__.py` (lines 58–83)

- [ ] **Step 1: Add imports and extend the authenticated block**

In `app/__init__.py`, add the imports for the helper inside `inject_tour_state` (deferred imports, same pattern as `Innplassering`/`TurnusSet`). Find the authenticated `return` dict (line 73) and add `pdf_downloads` to it. Also add `pdf_downloads` to the unauthenticated return (line 83).

The full updated `inject_tour_state` function:

```python
@app.context_processor
def inject_tour_state():
    if current_user.is_authenticated:
        from app.models import Innplassering, TurnusSet
        from app.utils.pdf_downloads import get_pdf_downloads
        from app.utils.turnus_helpers import get_user_turnus_set
        from flask import url_for
        db_session = get_db_session()
        try:
            db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
            has_min_turnus = False
            if db_user and db_user.rullenummer:
                active_ts = db_session.query(TurnusSet).filter_by(is_active=1).first()
                if active_ts:
                    has_min_turnus = db_session.query(Innplassering).filter_by(
                        turnus_set_id=active_ts.id,
                        rullenummer=str(db_user.rullenummer),
                    ).first() is not None

            turnus_set = get_user_turnus_set()
            pdf_downloads = []
            if turnus_set:
                year_id = turnus_set["year_identifier"].lower()
                raw = get_pdf_downloads(AppConfig.turnusfiler_dir, year_id)
                pdf_downloads = [
                    {
                        "display_name": item["display_name"],
                        "url": url_for(
                            "static",
                            filename=f'turnusfiler/{year_id}/pdf/{item["filename"]}',
                        ),
                    }
                    for item in raw
                ]

            return {
                "has_seen_tour": session.get('has_seen_tour', 0),
                "has_seen_favorites_tour": session.get('has_seen_favorites_tour', 0),
                "has_seen_mintur_tour": session.get('has_seen_mintur_tour', 0),
                "has_seen_compare_tour": session.get('has_seen_compare_tour', 0),
                "has_seen_welcome": session.get('has_seen_welcome', 0),
                "has_min_turnus": has_min_turnus,
                "pdf_downloads": pdf_downloads,
            }
        finally:
            db_session.close()
    return {
        "has_seen_tour": 0,
        "has_seen_favorites_tour": 0,
        "has_seen_mintur_tour": 0,
        "has_seen_compare_tour": 0,
        "has_seen_welcome": 0,
        "has_min_turnus": False,
        "pdf_downloads": [],
    }
```

- [ ] **Step 2: Run existing tests — expect all PASS (no regressions)**

```bash
pytest -x -q
```

Expected: all tests pass (no regressions from context processor change)

- [ ] **Step 3: Commit**

```bash
git add app/__init__.py
git commit -m "feat: inject pdf_downloads into all templates via context processor"
```

---

## Task 3: Update navbar template

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Replace the single download link with a submenu (lines 164–168)**

Find this block in `base.html`:

```html
                    <li>
                      <a class="dropdown-item" href="{{ url_for('downloads.download_pdf') }}">
                        <i class="bi bi-file-earmark-zip"></i> Lagre orginal Turnusliste (PDF)
                      </a>
                    </li>
```

Replace with:

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

- [ ] **Step 2: Add the JS toggle function alongside `toggleTurnusSubmenu`**

Find the existing `<script>` block (around line 239) that contains `toggleTurnusSubmenu`. Add `toggleDownloadsSubmenu` immediately after it, before `</script>`:

```javascript
        function toggleDownloadsSubmenu(event) {
          event.preventDefault();
          event.stopPropagation();

          const submenu = document.getElementById('downloads-submenu');
          const chevron = document.getElementById('downloads-chevron');

          if (submenu.style.display === 'none' || submenu.style.display === '') {
            submenu.style.display = 'block';
            chevron.classList.remove('bi-chevron-right');
            chevron.classList.add('bi-chevron-down');
          } else {
            submenu.style.display = 'none';
            chevron.classList.remove('bi-chevron-down');
            chevron.classList.add('bi-chevron-right');
          }
        }
```

- [ ] **Step 3: Verify manually**

1. Place a PDF in `app/static/turnusfiler/r26/pdf/` (e.g., copy an existing PDF there)
2. Run `python run.py`
3. Log in, open the user dropdown in the navbar
4. Confirm "Last ned PDF" appears with a chevron
5. Click it — submenu expands with the PDF's title-cased display name
6. Click the PDF link — it downloads
7. Switch to a year with no `pdf/` directory ("velg turnusår") — confirm the menu item disappears
8. Switch back — confirm it reappears

- [ ] **Step 4: Run all tests**

```bash
pytest -x -q
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: replace download link with dynamic PDF submenu in navbar"
```

---

## Verification Checklist

- [ ] `pytest tests/test_pdf_downloads.py -v` — 7 tests pass
- [ ] `pytest -x -q` — no regressions
- [ ] Navbar shows "Last ned PDF" submenu when `pdf/` dir has files
- [ ] Submenu hidden when `pdf/` dir is absent or empty
- [ ] Display names are title-cased with `r\d+_` prefixes stripped
- [ ] Files actually download on click
- [ ] Unauthenticated users see no download menu (no `UndefinedError`)
