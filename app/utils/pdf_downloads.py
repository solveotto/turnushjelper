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
        if not os.path.isfile(os.path.join(pdf_dir, filename)):
            continue
        if not filename.lower().endswith(".pdf"):
            continue
        name = os.path.splitext(filename)[0]
        name = re.sub(r"^[Rr]\d+_", "", name)
        results.append({"filename": filename, "display_name": name.title()})
    return results
