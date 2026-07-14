"""Form-validation tests.

Focus: CreateTurnusSetForm.year_identifier must reject values that could act as
path-traversal payloads, since it becomes a filesystem path component in the
turnus create/refresh routes.
"""

import pytest


def _validate_year_identifier(app, value):
    """Return the CreateTurnusSetForm.errors after validating a POST with the
    given year_identifier (CSRF is disabled by the test `app` fixture)."""
    from app.forms import CreateTurnusSetForm

    with app.test_request_context(
        method="POST",
        data={
            "name": "Some Turnus Set",
            "year_identifier": value,
            "use_existing_files": "y",
        },
    ):
        form = CreateTurnusSetForm()
        form.validate()
        return form.errors


class TestYearIdentifierValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            "../../etc",
            "../r26",
            "r26/..",
            "a/b",
            "a.b",          # dot could be used in traversal / hidden files
            "r26\\x",       # backslash
            "r 26",         # whitespace
            "R26;rm",       # shell-ish junk
        ],
    )
    def test_rejects_path_traversal_and_specials(self, app, payload):
        errors = _validate_year_identifier(app, payload)
        assert "year_identifier" in errors

    @pytest.mark.parametrize("payload", ["R25", "R26", "T26", "OSL01", "r26"])
    def test_accepts_valid_alphanumeric_identifiers(self, app, payload):
        errors = _validate_year_identifier(app, payload)
        assert "year_identifier" not in errors
