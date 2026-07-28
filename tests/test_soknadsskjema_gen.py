"""Smoke tests for søknadsskjema document generation.

The builders were extracted from `app/routes/shifts/soknadsskjema.py` into
`app/utils/soknadsskjema_gen.py` (Phase 3 item 4). They had no coverage at the
time, so these lock in the behaviour that matters: both formats build without
error, and the caller's data actually reaches the output.

They are pure functions — no app context, no DB — so no fixtures are needed.
"""

import zipfile

import pytest

from app.utils.soknadsskjema_gen import (
    build_soknadsskjema_doc,
    build_soknadsskjema_pdf,
)

fitz = pytest.importorskip("fitz")

DATO = "28.07.2026"
RULLENR_OG_NAVN = "Rullenr.: 1234 - Test Testesen"
STASJONERINGSSTED = "Oslo S"
KOMMENTARER = "En unik kommentar"
FAVORITES = ["OSL_01", "OSL_02"]

# Not boilerplate: the blank form already prints "Linje 1,3,5 eller 2,4,6", so a
# prioritering of "1,3,5" would appear even when choices are ignored entirely.
PRIORITERING = "6,5,4"

CHOICES = {
    "OSL_01": {
        "linje_135": True,
        "linje_246": False,
        "h_dag": True,
        "linjeprioritering": PRIORITERING,
    }
}

ARGS = (DATO, RULLENR_OG_NAVN, STASJONERINGSSTED, KOMMENTARER, FAVORITES)


def _docx_text(doc):
    """All non-empty text in the document, paragraphs and table cells."""
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(p for p in parts if p.strip())


def _pdf_text(buf):
    doc = fitz.open(stream=buf.read(), filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


class TestBuildDoc:
    def test_produces_a_valid_docx_container(self, tmp_path):
        doc = build_soknadsskjema_doc(*ARGS, choices=CHOICES)
        path = tmp_path / "soknadsskjema.docx"
        doc.save(str(path))

        # A .docx is a zip; a corrupt build usually fails here first.
        assert zipfile.is_zipfile(path)
        assert path.stat().st_size > 10_000

    def test_user_input_reaches_the_document(self):
        text = _docx_text(build_soknadsskjema_doc(*ARGS, choices=CHOICES))

        assert DATO in text
        assert "1234" in text
        assert STASJONERINGSSTED in text
        assert KOMMENTARER in text

    def test_favorites_are_listed_in_display_form(self):
        """Titles are rendered with the underscore stripped: OSL_01 -> 'OSL 01'."""
        text = _docx_text(build_soknadsskjema_doc(*ARGS, choices=CHOICES))

        assert "OSL 01" in text
        assert "OSL 02" in text

    def test_builds_without_choices(self):
        doc = build_soknadsskjema_doc(*ARGS, choices=None)

        assert "OSL 01" in _docx_text(doc)


class TestBuildPdf:
    def test_produces_a_well_formed_pdf(self):
        data = build_soknadsskjema_pdf(*ARGS, choices=CHOICES).read()

        assert data[:4] == b"%PDF"
        assert b"%%EOF" in data[-1024:]

    def test_user_input_reaches_the_pdf(self):
        text = _pdf_text(build_soknadsskjema_pdf(*ARGS, choices=CHOICES))

        assert DATO in text
        assert "1234" in text
        assert STASJONERINGSSTED in text
        assert KOMMENTARER in text
        assert "OSL 01" in text

    def test_builds_without_choices(self):
        text = _pdf_text(build_soknadsskjema_pdf(*ARGS, choices=None))

        assert "OSL 01" in text


class TestChoicesPropagate:
    """The choices dict must actually reach the output, in both formats.

    Without this the builders could ignore `choices` entirely and every other
    assertion here would still pass.
    """

    def test_prioritering_in_docx_only_when_given(self):
        with_choices = _docx_text(build_soknadsskjema_doc(*ARGS, choices=CHOICES))
        without = _docx_text(build_soknadsskjema_doc(*ARGS, choices=None))

        assert PRIORITERING in with_choices
        assert PRIORITERING not in without

    def test_prioritering_in_pdf_only_when_given(self):
        with_choices = _pdf_text(build_soknadsskjema_pdf(*ARGS, choices=CHOICES))
        without = _pdf_text(build_soknadsskjema_pdf(*ARGS, choices=None))

        assert PRIORITERING in with_choices
        assert PRIORITERING not in without
