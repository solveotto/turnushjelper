import logging
import os
import tempfile
from datetime import date

from flask import Blueprint, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required

from app.database import get_db_session
from app.extensions import cache
from app.models import DBUser
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set

logger = logging.getLogger(__name__)


def _turnusliste_cache_key():
    """Per-user, per-turnus-set cache key for the /turnusliste response."""
    ts = get_user_turnus_set()
    ts_id = ts['id'] if ts else 'none'
    return f"view/turnusliste/{current_user.get_id()}/{ts_id}"

shifts = Blueprint("shifts", __name__)


@shifts.route("/")
@login_required
def index():
    return redirect(url_for("shifts.turnusliste"))


@shifts.route("/turnusliste")
@login_required
@cache.cached(timeout=120, key_prefix=_turnusliste_cache_key)
def turnusliste():
    # Get the turnus set for this user (their choice or system default)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = db_utils.get_active_turnus_set()

    # Get favorites for current user and active turnus set
    favoritt = (
        db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)
        if current_user.is_authenticated
        else []
    )

    # Create a position lookup dictionary for robust favorite numbering
    favorite_positions = {name: idx + 1 for idx, name in enumerate(favoritt)}

    # Load data for user's selected year
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    # Get turnus parameter for highlighting specific turnus
    highlighted_turnus = request.args.get("turnus")

    return render_template(
        "turnusliste.html",
        page_name="Turnusliste",
        table_data=user_df_manager.turnus_data,
        df=user_df_manager.df.to_dict(orient="records")
        if not user_df_manager.df.empty
        else [],
        favoritt=favoritt,
        favorite_positions=favorite_positions,
        current_turnus_set=user_turnus_set,
        active_set=active_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
        highlighted_turnus=highlighted_turnus,
    )


@shifts.route("/switch-year/<int:turnus_set_id>")
@login_required
def switch_user_year(turnus_set_id):
    """Allow user to switch which year they're viewing (stored in session)"""
    # Invalidate cached page for the previous turnus set before switching
    cache.delete(_turnusliste_cache_key())
    # Store user's choice in their session
    session["user_selected_turnus_set"] = turnus_set_id

    # Get the referring page (where user came from)
    next_page = request.args.get("next") or request.referrer

    # If no referrer or if it's the same switch route, default to turnusliste
    if not next_page or "/switch-year/" in next_page:
        next_page = url_for("shifts.turnusliste")

    return redirect(next_page)


@shifts.route("/favorites")
@login_required
def favorites():
    # Get user's selected turnus set (same logic as turnusliste)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = db_utils.get_active_turnus_set()

    # Get favorites for the user's selected turnus set
    fav_order_lst = db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)

    # Load data for the user's selected turnus set
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    fav_dict_lookup = {}

    # Use the user's selected turnus data, not global data
    for x in user_df_manager.turnus_data:
        for name, data in x.items():
            if name in fav_order_lst:
                fav_dict_lookup[name] = data
    fav_dict_sorted = [
        {name: fav_dict_lookup[name]}
        for name in fav_order_lst
        if name in fav_dict_lookup
    ]

    return render_template(
        "favorites.html",
        page_name="Favoritter",
        favorites=fav_dict_sorted,
        df=user_df_manager.df.to_dict(orient="records")
        if not user_df_manager.df.empty
        else [],
        current_turnus_set=user_turnus_set,
        active_set=active_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )


@shifts.route("/compare")
@login_required
def compare():
    # Get user's selected turnus set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Load data for user's selected year
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    # Prepare metrics for charts
    df = user_df_manager.df
    metrics = ["natt", "tidlig", "shift_cnt", "before_6", "helgetimer",
               "tidlig_6_8", "tidlig_8_12", "longest_off_streak", "longest_work_streak", "avg_shift_hours"]
    labels = df["turnus"].tolist() if not df.empty else []
    data = {m: df[m].tolist() if m in df else [] for m in metrics}

    return render_template(
        "compare.html",
        page_name="Sammenlign Turnuser",
        labels=labels,
        data=data,
        current_turnus_set=user_turnus_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )


@shifts.route("/turnusnokkel/<int:turnus_set_id>/<turnus_name>")
@login_required
def turnusnokkel_view(turnus_set_id, turnus_name):
    import os
    import openpyxl
    from config import AppConfig

    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    year_identifier = turnus_set['year_identifier']
    df_manager = df_utils.DataframeManager(turnus_set_id)

    # Build linje_shifts[linje_nr (1-6)][dag_nr (1-7)] = time_string
    linje_shifts = {}
    for t in df_manager.turnus_data:
        if turnus_name not in t:
            continue
        target_data = t[turnus_name]
        week_items = [(k, v) for k, v in target_data.items() if isinstance(v, dict)]
        for uke_nr, ukedata in sorted(week_items, key=lambda x: int(x[0])):
            linje = int(uke_nr)
            linje_shifts[linje] = {}
            for dag_nr, dag_data in ukedata.items():
                if not isinstance(dag_data, dict):
                    continue
                tid = dag_data.get('tid', [])
                if len(tid) >= 2:
                    value = f"{tid[0]} - {tid[1]}"
                elif tid:
                    value = tid[0]
                else:
                    value = ''
                linje_shifts[linje][int(dag_nr)] = {
                    'value': value,
                    'dagsverk': dag_data.get('dagsverk', ''),
                }
        break

    dag_names = ['Man', 'Tirs', 'Ons', 'Tors', 'Fre', 'Lør', 'Søn']
    linje_labels = ['Linje 1', 'Linje 2', 'Linje 3', 'Linje 4', 'Linje 5', 'Linje 6']

    # Read template to get calendar week labels for each of the 6 rotation groups.
    # The template has 6 groups of 8 rows (1 header + 7 day rows).
    # Each group header has Uke labels in columns H–P (0-indexed 7–15).
    # For group g (0-indexed), Linje column j (1-indexed):
    #   shift data comes from Linje ((g + j - 1) % 6 + 1).
    template_path = os.path.join(
        AppConfig.turnusfiler_dir, year_identifier.lower(),
        f'turnusnøkkel_{year_identifier}_org.xlsx'
    )
    groups = []
    template_found = os.path.exists(template_path)

    if template_found:
        wb = openpyxl.load_workbook(template_path, data_only=True)
        sheet = wb['Turnusnøkkel']
        all_rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=48)]
        wb.close()

        for g in range(6):
            header_cells = all_rows[g * 8]
            uke_labels = [str(c.value) for c in header_cells[7:16] if c.value is not None]
            day_rows = []
            for d in range(7):
                _empty = {'value': '', 'dagsverk': ''}
                cells = []
                for j in range(1, 7):
                    linje_idx = (g + j - 1) % 6 + 1
                    cells.append(linje_shifts.get(linje_idx, {}).get(d + 1, _empty))
                dates = []
                for cell in all_rows[g * 8 + 1 + d][7:16]:
                    if cell.value is not None and hasattr(cell.value, 'strftime'):
                        is_holiday = (
                            cell.font and cell.font.color
                            and cell.font.color.type == 'rgb'
                            and cell.font.color.rgb == 'FFFF0000'
                        )
                        dates.append({'value': cell.value.strftime('%d.%m.%y'), 'holiday': bool(is_holiday)})
                    else:
                        dates.append({'value': '', 'holiday': False})
                day_rows.append({'name': dag_names[d], 'cells': cells, 'dates': dates})
            groups.append({'uke_labels': uke_labels, 'day_rows': day_rows})
    else:
        # Fallback: simple 6×7 table without calendar mapping
        for g in range(6):
            day_rows = []
            for d in range(7):
                _empty = {'value': '', 'dagsverk': ''}
                cells = [linje_shifts.get(g + 1, {}).get(d + 1, _empty)] + [_empty] * 5
                day_rows.append({'name': dag_names[d], 'cells': cells, 'dates': [], 'is_saturday': d == 5, 'is_sunday': d == 6})
            groups.append({'uke_labels': [f'Linje {g + 1}'], 'day_rows': day_rows})

    return render_template('turnusnokkel_print.html',
        turnus_name=turnus_name,
        year_identifier=year_identifier,
        turnus_set_id=turnus_set_id,
        linje_labels=linje_labels,
        groups=groups,
        template_found=template_found)


def _set_table_col_widths(table, col_widths_dxa):
    """Set explicit tblGrid and per-cell tcW widths for cross-app compatibility.

    IMPORTANT: call this AFTER all cell merges so that gridSpan is already set
    and tcW can reflect the correct merged width. Using row._tr.iterchildren()
    instead of row.cells avoids the python-docx behaviour of returning the same
    merged cell object multiple times (once per logical column it spans), which
    would produce wrong tcW values and cause the sum of per-row tcW to diverge
    from tblW — a mismatch OpenOffice treats as a fatal table error.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))

    # Total table width
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(sum(col_widths_dxa)))
    tblW.set(qn("w:type"), "dxa")

    # Replace tblGrid so renderers know exact column widths
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    new_grid = OxmlElement("w:tblGrid")
    for w in col_widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        new_grid.append(gc)
    tblPr.addnext(new_grid)

    # Per-cell explicit widths — iterate actual <w:tc> elements, not row.cells.
    # row.cells expands merged cells into one entry per logical column, so a cell
    # with gridSpan=2 appears twice; iterchildren gives exactly one entry per
    # physical cell, matching the gridSpan already written by merge().
    for row in table.rows:
        ci = 0
        for tc in row._tr.iterchildren(qn("w:tc")):
            if ci >= len(col_widths_dxa):
                break
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is None:
                tcPr = OxmlElement("w:tcPr")
                tc.insert(0, tcPr)
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                tcPr.insert(0, tcW)
            grid_span = tcPr.find(qn("w:gridSpan"))
            span = int(grid_span.get(qn("w:val"), 1)) if grid_span is not None else 1
            tcW.set(qn("w:w"), str(sum(col_widths_dxa[ci:ci + span])))
            tcW.set(qn("w:type"), "dxa")
            ci += span


def _arial(run, size_pt, bold=False):
    from docx.shared import Pt
    run.font.name = "Arial"
    run.font.size = Pt(size_pt)
    if bold:
        run.font.bold = True


def _build_soknadsskjema_doc(dato, rullenr_og_navn, stasjoneringssted, kommentarer, favorites):
    """Generate søknadsskjema from scratch matching the original form layout.

    Layout (top to bottom):
      1. Title
      2. "Unngå stifter og tape..." instruction
      3. Personal info table (Dato / Rullenr. / Stasjoneringssted / Kommentarer)
      4. Instruction text about Linje (with bold + partial underlines)
      5. Alt table (71 rows, merges done BEFORE _set_table_col_widths)

    The merge-before-widths order is critical: python-docx's row.cells expands
    merged cells (one entry per logical column), so calling _set_table_col_widths
    before merging leaves merged cells with single-column tcW. The resulting
    tcW-sum < tblW mismatch is treated as a fatal table error by OpenOffice.
    """
    from docx import Document
    from docx.shared import Pt

    doc = Document()

    # Page: A4, margins matching original
    section = doc.sections[0]
    section.page_width = Pt(595)
    section.page_height = Pt(842)
    section.left_margin = Pt(71)
    section.right_margin = Pt(71)
    section.top_margin = Pt(27)
    section.bottom_margin = Pt(35)

    # Strip python-docx default 8 pt space-after + 1.15× line spacing from Normal
    normal = doc.styles["Normal"]
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    for p in list(doc.paragraphs):
        p._element.getparent().remove(p._element)

    def _p(text="", size_pt=11, bold=False):
        para = doc.add_paragraph()
        if text:
            _arial(para.add_run(text), size_pt, bold)
        return para

    def _mixed(size_pt=11, *parts):
        """Paragraph with mixed runs: each part is (text, bold, underline)."""
        para = doc.add_paragraph()
        for text, bold, underline in parts:
            r = para.add_run(text)
            _arial(r, size_pt, bold)
            if underline:
                r.font.underline = True
        return para

    # ── Title ──
    _p("Søknad turplassering for              Lokomotivpersonalet", 16, bold=True)

    # ── Top instruction ──
    _p()
    _p("Unngå stifter og tape")
    _p("Bruk helst ensidig og merk hver ark med navn og rullenr")

    # ── Personal info table ──
    _p()
    P_COL_WIDTHS = [2856, 6204]  # sum = 9060 dxa
    p_tbl = doc.add_table(rows=4, cols=2, style="Table Grid")
    _set_table_col_widths(p_tbl, P_COL_WIDTHS)
    for i, (label, value) in enumerate([
        ("Dato", dato),
        ("Rullenr. og navn", rullenr_og_navn),
        ("Stasjoneringsted", stasjoneringssted),
        ("Evt. kommentarer", kommentarer),
    ]):
        _arial(p_tbl.rows[i].cells[0].paragraphs[0].add_run(label), 11, bold=True)
        _arial(p_tbl.rows[i].cells[1].paragraphs[0].add_run(value), 11)

    # ── Middle instruction (comes AFTER personal info table, matching original layout) ──
    _p()
    _mixed(11, ("Linje er ", True, False), ("uten", True, True), (" betydning:", True, False))
    _p("Fyll kun ut kolonne 1.")
    _p("Du plasseres i vilkårlig valgt linje.")
    _mixed(11, ("Kun ", True, False), ("helg", True, True), (" er av betydning:", True, False))
    _p("Fyll ut kolonne 1 og 2")
    _p("Du plasseres i vilkårlig valgt linje innenfor din helg (Linje 1,3,5 eller 2,4,6)")
    _mixed(11, ("Linje", True, True), (" er av betydning", True, False))
    _p("Fyll ut kolonne 1 og 3")
    _mixed(11,
        ("Skriv linjer i ", False, False),
        ("prioritert rekkefølge", False, True),
        (" i kolonne 3. Du søker kun de linjene som er ført opp.", False, False),
    )

    # ── Alt table ──
    # Widths scaled from original proportions to text area (9060 dxa = 595pt − 2×71pt).
    COL_WIDTHS = [805, 841, 1459, 1497, 3010, 1448]  # sum = 9060 dxa

    alt_tbl = doc.add_table(rows=3 + 71, cols=6, style="Table Grid")

    def _cell(r, c, text, size_pt=10, bold=False):
        _arial(alt_tbl.cell(r, c).paragraphs[0].add_run(text), size_pt, bold)

    # Merges FIRST so gridSpan is set before _set_table_col_widths reads it
    alt_tbl.cell(0, 0).merge(alt_tbl.cell(0, 1))
    alt_tbl.cell(0, 2).merge(alt_tbl.cell(0, 3))
    alt_tbl.cell(1, 0).merge(alt_tbl.cell(1, 1))
    alt_tbl.cell(1, 2).merge(alt_tbl.cell(1, 3))

    _set_table_col_widths(alt_tbl, COL_WIDTHS)

    # Header row 0: Kolonne labels
    _cell(0, 0, "Kolonne 1", bold=True)
    _cell(0, 2, "Kolonne 2", bold=True)
    _cell(0, 4, "Kolonne 3", bold=True)
    _cell(0, 5, "Kolonne 4", bold=True)

    # Header row 1: column descriptions (matching original text)
    _cell(1, 0, "Tur\nnummer:")
    _cell(1, 2, "Ønsker en av følgende linjer:\n(Sett X)\n(Ingen prioritering blant disse)")
    _cell(1, 4, "Linjeprioritering\n(Skriv inn de linjene du ønsker i prioritert rekkefølge)")
    _cell(1, 5, "H-dag\n(Skriv J for jobb.\nBlankt felt gir fri)")

    # Header row 2: sub-column labels + down arrow indicating Tur nummer entry column
    _cell(2, 1, "↓")
    _cell(2, 2, "Linje 1,3,5")
    _cell(2, 3, "Linje 2,4,6")

    # Data rows: Alt.1 – Alt.71
    for i in range(71):
        _cell(3 + i, 0, f"Alt.{i + 1}")
        if i < len(favorites):
            _cell(3 + i, 1, favorites[i])

    return doc


@shifts.route("/soknadsskjema", methods=["GET", "POST"])
@login_required
def soknadsskjema():
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    user_id = current_user.get_id()

    fav_order_lst = db_utils.get_favorite_lst(user_id, turnus_set_id)

    # Pre-populate personal info from DBUser
    db_session = get_db_session()
    try:
        db_user = db_session.query(DBUser).filter_by(id=user_id).first()
        user_name = (db_user.name or "") if db_user else ""
        user_rullenummer = (db_user.rullenummer or "") if db_user else ""
        user_stasjoneringssted = (db_user.stasjoneringssted or "") if db_user else ""
    finally:
        db_session.close()

    if request.method == "POST":
        dato = request.form.get("dato", "")
        rullenr_og_navn = request.form.get("rullenr_og_navn", "")
        stasjoneringssted = request.form.get("stasjoneringssted", "")
        kommentarer = request.form.get("kommentarer", "")

        try:
            doc = _build_soknadsskjema_doc(
                dato, rullenr_og_navn, stasjoneringssted, kommentarer, fav_order_lst
            )

            year_id = user_turnus_set["year_identifier"] if user_turnus_set else "turnus"
            filename = f"soknadsskjema_{year_id}.docx"

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
            temp_file_path = temp_file.name
            temp_file.close()
            doc.save(temp_file_path)

            response = send_file(
                temp_file_path,
                as_attachment=True,
                download_name=filename,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

            @response.call_on_close
            def cleanup():
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

            return response

        except Exception as e:
            logger.error("Error generating soknadsskjema: %s", e)
            from flask import flash
            flash("Feil ved generering av søknadsskjema. Prøv igjen.", "danger")

    # GET (and POST error fallback)
    default_rullenr_navn = f"{user_rullenummer} {user_name}".strip()
    return render_template(
        "søknadsskjema.html",
        page_name="Søknadsskjema",
        favorites=fav_order_lst,
        current_turnus_set=user_turnus_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
        today=date.today().strftime("%d.%m.%Y"),
        default_rullenr_navn=default_rullenr_navn,
        default_stasjoneringssted=user_stasjoneringssted,
    )


@shifts.route("/import-favorites")
@login_required
def import_favorites():
    """Page for importing favorites from previous turnus years based on shift statistics."""
    from app.utils import shift_matcher

    # Get user's current turnus set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Get turnus sets where user has favorites
    user_id = current_user.get_id()
    sets_with_stats = shift_matcher.get_all_turnus_sets_with_stats()

    available_sources = []
    for ts in sets_with_stats:
        if ts["id"] == turnus_set_id:
            continue
        favorites = db_utils.get_favorite_lst(user_id, ts["id"])
        if favorites:
            ts["favorite_count"] = len(favorites)
            available_sources.append(ts)

    return render_template(
        "import_favorites.html",
        page_name="Importer Favoritter",
        current_turnus_set=user_turnus_set,
        available_sources=available_sources,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )
