"""A failed strekliste regeneration must not destroy the working image set.

`generate_all_images(force=True)` used to delete every PNG before rendering the
replacements. That takes ~35 s for a 423-shift set, against gunicorn's default
30 s worker timeout, so the admin button reproducibly killed the worker partway
and left a truncated set behind — which looks correct until someone opens a
high-numbered shift. Generation now builds into a sibling temp directory and
swaps it in only on success.
"""

import os

import pytest

from app.utils.pdf import strekliste_generator as sg


def _png(directory, name, body=b"old"):
    path = os.path.join(directory, f"{name}.png")
    with open(path, "wb") as f:
        f.write(body)
    return path


@pytest.fixture
def image_dirs(tmp_path):
    """A populated live directory plus a freshly built replacement."""
    live = tmp_path / "png"
    live.mkdir()
    for n in ("1001", "1002", "1003"):
        _png(str(live), n, b"old")

    work = tmp_path / ".png-gen-abc"
    work.mkdir()
    for n in ("2001", "2002"):
        _png(str(work), n, b"new")

    return str(live), str(work)


class TestSwapIn:
    def test_replaces_contents_wholesale(self, image_dirs):
        live, work = image_dirs

        sg._swap_in(work, live)

        assert sorted(os.listdir(live)) == ["2001.png", "2002.png"]
        assert open(os.path.join(live, "2001.png"), "rb").read() == b"new"

    def test_leaves_no_temp_or_backup_dirs_behind(self, image_dirs, tmp_path):
        live, work = image_dirs

        sg._swap_in(work, live)

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "png"]
        assert leftovers == []

    def test_works_when_no_live_directory_exists(self, tmp_path):
        work = tmp_path / ".png-gen-xyz"
        work.mkdir()
        _png(str(work), "3001", b"new")
        live = str(tmp_path / "png")

        sg._swap_in(str(work), live)

        assert os.listdir(live) == ["3001.png"]


class TestInterruptedRunIsNonDestructive:
    def test_failure_partway_leaves_the_live_set_intact(self, tmp_path, monkeypatch):
        """The regression: a run that dies mid-render must not eat the old images."""
        base = tmp_path / "streklister"
        live = base / "png"
        live.mkdir(parents=True)
        for n in ("1001", "1002", "1003"):
            _png(str(live), n, b"old")
        pdf = base / "r26_streker.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        monkeypatch.setattr(sg, "get_paths", lambda v: {
            "pdf_path": str(pdf), "images_dir": str(live),
            "pdf_exists": True, "images_dir_exists": True,
        })

        # Fail the way a real interruption does: partway through, after the
        # temp directory has been created.
        def boom(*a, **kw):
            raise RuntimeError("worker killed")

        monkeypatch.setattr(sg, "_generate_into", boom)

        with pytest.raises(RuntimeError):
            sg.generate_all_images("r26", force=True)

        assert sorted(os.listdir(str(live))) == ["1001.png", "1002.png", "1003.png"]
        assert open(os.path.join(str(live), "1001.png"), "rb").read() == b"old"

    def test_failure_cleans_up_the_temp_directory(self, tmp_path, monkeypatch):
        base = tmp_path / "streklister"
        live = base / "png"
        live.mkdir(parents=True)
        pdf = base / "r26_streker.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        monkeypatch.setattr(sg, "get_paths", lambda v: {
            "pdf_path": str(pdf), "images_dir": str(live),
            "pdf_exists": True, "images_dir_exists": True,
        })
        monkeypatch.setattr(sg, "_generate_into", lambda *a, **kw: 1 / 0)

        with pytest.raises(ZeroDivisionError):
            sg.generate_all_images("r26", force=True)

        strays = [p.name for p in base.iterdir() if p.name.startswith(".png-gen-")]
        assert strays == []
