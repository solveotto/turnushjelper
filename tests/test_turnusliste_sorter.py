"""Guards the slider ids shared by the sorter markup and sorting-system.js.

The panel renders from one Jinja macro (components/sorter_controls.html) but the
JS reaches every slider by literal id — sortTurnuser(), saveSortingSettings()
and applySavedSettings() all do unguarded document.getElementById(...).value,
and initializeSorting() gates the whole module on #helgetimer-slider existing.
A renamed or mistyped macro argument therefore kills sorting silently, with no
console error until a user drags something.

So rather than restate a list here, these tests read the ids the JS actually
asks for and assert the page renders each one, in both the desktop and the
-mobile variant.
"""

import re
from pathlib import Path

from app.models import TurnusSet
from tests.conftest import login_user

SORTING_JS = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "static"
    / "js"
    / "modules"
    / "sorting-system.js"
)


def _slider_ids_required_by_js():
    """Every '<name>-slider' id sorting-system.js looks up by hand."""
    source = SORTING_JS.read_text(encoding="utf-8")
    ids = set(re.findall(r"getElementById\(\s*'([a-z0-9-]+-slider)'\s*\)", source))
    ids.update(re.findall(r"querySelector\(\s*'#([a-z0-9-]+-slider)'\s*\)", source))
    return sorted(ids)


def _render_turnusliste(client, sample_user, db_session):
    db_session.add(TurnusSet(name="R26", year_identifier="R26", is_active=1))
    db_session.commit()
    login_user(client, sample_user["username"], sample_user["password"])

    resp = client.get("/turnusliste")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_js_asks_for_the_eleven_known_sliders():
    """Fails if a criterion is added to the JS without extending the macro."""
    assert _slider_ids_required_by_js() == [
        "before-6-slider",
        "ettermiddag-slider",
        "helgetimer-slider",
        "kompdager-slider",
        "longest-off-slider",
        "longest-streak-slider",
        "natt-slider",
        "shift-cnt-slider",
        "tidlig-6-8-slider",
        "tidlig-8-12-slider",
        "tidlig-slider",
    ]


def test_every_slider_the_js_needs_renders(client, sample_user, db_session):
    html = _render_turnusliste(client, sample_user, db_session)

    for slider_id in _slider_ids_required_by_js():
        # Desktop dropdown and mobile modal, plus the value chip
        # updateSliderValue() derives by replacing '-slider' with '-value'.
        assert f'id="{slider_id}"' in html, f"missing desktop slider {slider_id}"
        assert f'id="{slider_id}-mobile"' in html, f"missing mobile slider {slider_id}"
        value_id = slider_id.replace("-slider", "-value")
        assert f'id="{value_id}"' in html, f"missing value chip {value_id}"
        assert f'id="{value_id}-mobile"' in html, f"missing chip {value_id}-mobile"


def test_sliders_are_labelled(client, sample_user, db_session):
    """Every range input needs a <label for> — screen readers announce nothing
    without it, which is the state the panel shipped in before this."""
    html = _render_turnusliste(client, sample_user, db_session)

    for slider_id in _slider_ids_required_by_js():
        for full_id in (slider_id, f"{slider_id}-mobile"):
            assert f'for="{full_id}"' in html, f"unlabelled slider {full_id}"


def test_reset_and_done_controls_render(client, sample_user, db_session):
    html = _render_turnusliste(client, sample_user, db_session)

    assert 'id="reset-sorting"' in html
    assert 'id="reset-sorting-mobile"' in html
    # Ferdig closes the dropdown from JS; data-bs-toggle would be a no-op here.
    assert 'id="sorter-done"' in html
    assert 'data-bs-auto-close="outside"' in html
