import os


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
