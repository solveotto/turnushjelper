import io
import os
from datetime import datetime

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user

from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.models import DBUser, Favorites
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils, df_utils


def _member_excel_path():
    """Storage path for the uploaded NLF member list."""
    return os.path.join(
        current_app.root_path, "static", "turnusfiler", "medlemsliste.xlsx"
    )


@admin.route("/employees")
@admin_required
def manage_employees():
    """List all employees (stub and registered) from the seniority list."""
    employees = user_service.get_all_stub_users()

    registered_list = []
    stub_list       = []
    not_on_list     = []
    system_list     = []

    for emp in employees:
        if not emp.get("rullenummer") and not emp.get("medlemsnummer"):
            # No identifiers → admin / system account
            system_list.append(emp)
        elif emp.get("seniority_nr"):
            # Has seniority_nr → matched to current PDF
            if emp.get("is_registered"):
                registered_list.append(emp)
            else:
                stub_list.append(emp)
        elif emp.get("is_registered"):
            registered_list.append(emp)
        elif emp.get("rullenummer"):
            # Has rullenummer but no seniority_nr → not on current PDF
            not_on_list.append(emp)
        else:
            # Medlemsnummer-only stub from the member list import
            stub_list.append(emp)

    pdf_path = os.path.join(
        current_app.root_path, "static", "turnusfiler", "ansinitet.pdf"
    )
    pdf_exists = os.path.exists(pdf_path)

    pdf_date = None
    if pdf_exists:
        from app.utils.pdf.employee_scraper import scrape_pdf_date
        pdf_date = scrape_pdf_date(pdf_path)

    excel_path = _member_excel_path()
    excel_exists = os.path.exists(excel_path)
    excel_date = None
    if excel_exists:
        try:
            from openpyxl import load_workbook as _load_wb
            wb = _load_wb(excel_path, read_only=True)
            created = wb.properties.created
            wb.close()
            if created:
                excel_date = created.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass
        if not excel_date:
            excel_date = datetime.fromtimestamp(os.path.getmtime(excel_path)).strftime(
                "%d.%m.%Y %H:%M"
            )

    review_list = [emp for emp in employees if emp.get("not_on_nlf_list")]
    member_report = session.pop("medlemsliste_report", None)

    return render_template(
        "admin_employees.html",
        page_name="Ansattliste",
        registered_list=registered_list,
        stub_list=stub_list,
        not_on_list=not_on_list,
        system_list=system_list,
        review_list=review_list,
        pdf_exists=pdf_exists,
        pdf_date=pdf_date,
        excel_exists=excel_exists,
        excel_date=excel_date,
        member_report=member_report,
    )


@admin.route("/upload-medlemsliste", methods=["POST"])
@admin_required
def upload_member_excel():
    """Upload the NLF member list (xlsx) and sync medlemsnummer into users."""
    from app.utils.member_excel import parse_member_excel

    if "excel_file" not in request.files or not request.files["excel_file"].filename:
        flash("Ingen fil valgt.", "danger")
        return redirect(url_for("admin.manage_employees"))

    excel_file = request.files["excel_file"]
    if not excel_file.filename.lower().endswith(".xlsx"):
        flash("Kun Excel-filer (.xlsx) er tillatt.", "danger")
        return redirect(url_for("admin.manage_employees"))

    excel_path = _member_excel_path()
    excel_file.save(excel_path)

    try:
        members = parse_member_excel(excel_path)
    except Exception as e:
        flash(f"Fil lagret, men feil ved lesing: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        report = user_service.sync_members_from_excel(members)
    except Exception as e:
        flash(f"Fil lagret, men feil ved synkronisering: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    msg = (
        f"Medlemsliste importert ({report['total_rows']} rader): "
        f"{report['matched']} matchet, {report['created']} nye stubber, "
        f"{report['unchanged']} uendret."
    )
    if report["updated"]:
        msg += f" {report['updated']} oppdatert."
    if report["deleted_stubs"]:
        msg += f" {report['deleted_stubs']} stubber slettet."
    if report["skipped_invalid"]:
        msg += f" {report['skipped_invalid']} ugyldige rader hoppet over."
    if report["conflicts"]:
        msg += f" {len(report['conflicts'])} konflikter."
    if report["flagged"]:
        msg += f" {report['flagged']} brukere flagget som ikke på NLF-listen."
    if report["unflagged"]:
        msg += f" {report['unflagged']} brukere gjenopprettet (funnet på listen igjen)."
    flash(msg, "warning" if report["conflicts"] else "success")

    session["medlemsliste_report"] = report
    return redirect(url_for("admin.manage_employees"))


@admin.route("/import-employees", methods=["POST"])
@admin_required
def import_employees():
    """Enrich existing member-list users with rullenummer/HR data from the seniority PDF."""
    from app.utils.pdf.employee_scraper import scrape_employees

    pdf_path = os.path.join(
        current_app.root_path, "static", "turnusfiler", "ansinitet.pdf"
    )
    if not os.path.exists(pdf_path):
        flash(f"PDF ikke funnet: {pdf_path}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        scraped = scrape_employees(pdf_path)
    except Exception as e:
        flash(f"Feil ved lesing av PDF: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        result = user_service.sync_employees_from_scrape(scraped)
        msg = (
            f"{result['updated']} oppdatert, {result['unchanged']} uendret "
            f"av {len(scraped)} totalt."
        )
        if result["merged_by_name"]:
            msg += f" {result['merged_by_name']} koblet til medlemsliste på navn."
        if result["merged_by_date"]:
            msg += f" {result['merged_by_date']} koblet til medlemsliste på ansettelsesdato."
        if result["skipped_unmatched"]:
            msg += (
                f" {result['skipped_unmatched']} ikke funnet på medlemslisten "
                f"— hoppet over."
            )
        flash(msg, "success")
    except Exception as e:
        flash(f"Feil ved import: {e}", "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/sync-members", methods=["POST"])
@admin_required
def sync_members():
    """Re-run member import on the already-stored medlemsliste.xlsx."""
    from app.utils.member_excel import parse_member_excel

    excel_path = _member_excel_path()
    if not os.path.exists(excel_path):
        flash("Ingen lagret medlemsliste funnet.", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        members = parse_member_excel(excel_path)
    except Exception as e:
        flash(f"Feil ved lesing av fil: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        report = user_service.sync_members_from_excel(members)
    except Exception as e:
        flash(f"Feil ved synkronisering: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    msg = (
        f"Medlemsliste synkronisert ({report['total_rows']} rader): "
        f"{report['matched']} matchet, {report['created']} nye stubber, "
        f"{report['unchanged']} uendret."
    )
    if report["updated"]:
        msg += f" {report['updated']} oppdatert."
    if report["deleted_stubs"]:
        msg += f" {report['deleted_stubs']} stubber slettet."
    if report["skipped_invalid"]:
        msg += f" {report['skipped_invalid']} ugyldige rader hoppet over."
    if report["conflicts"]:
        msg += f" {len(report['conflicts'])} konflikter."
    if report["flagged"]:
        msg += f" {report['flagged']} brukere flagget som ikke på NLF-listen."
    if report["unflagged"]:
        msg += f" {report['unflagged']} brukere gjenopprettet (funnet på listen igjen)."
    flash(msg, "warning" if report["conflicts"] else "success")

    session["medlemsliste_report"] = report
    return redirect(url_for("admin.manage_employees"))


@admin.route("/upload-ansinitet", methods=["POST"])
@admin_required
def upload_ansinitet_pdf():
    """Upload a new ansinitet.pdf, save it, then immediately sync employee data."""
    from app.utils.pdf.employee_scraper import scrape_employees

    if "pdf_file" not in request.files or not request.files["pdf_file"].filename:
        flash("Ingen fil valgt.", "danger")
        return redirect(url_for("admin.manage_employees"))

    pdf_file = request.files["pdf_file"]
    if not pdf_file.filename.lower().endswith(".pdf"):
        flash("Kun PDF-filer er tillatt.", "danger")
        return redirect(url_for("admin.manage_employees"))

    pdf_path = os.path.join(
        current_app.root_path, "static", "turnusfiler", "ansinitet.pdf"
    )
    pdf_file.save(pdf_path)

    try:
        scraped = scrape_employees(pdf_path)
    except Exception as e:
        flash(f"PDF lagret, men feil ved lesing: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        result = user_service.sync_employees_from_scrape(scraped)
        msg = (
            f"PDF lastet opp og synkronisert ({len(scraped)} ansatte i PDF): "
            f"{result['updated']} oppdatert, {result['unchanged']} uendret."
        )
        if result["merged_by_name"]:
            msg += f" {result['merged_by_name']} koblet til medlemsliste på navn."
        if result["merged_by_date"]:
            msg += f" {result['merged_by_date']} koblet til medlemsliste på ansettelsesdato."
        if result["removed_from_list"]:
            msg += f" {result['removed_from_list']} ikke lenger på lista."
        if result["skipped_unmatched"]:
            msg += (
                f" {result['skipped_unmatched']} ikke funnet på medlemslisten "
                f"— hoppet over."
            )
        flash(msg, "success")
    except Exception as e:
        flash(f"PDF lagret, men feil ved synkronisering: {e}", "danger")

    return redirect(url_for("admin.manage_employees"))


@admin.route("/sync-employees", methods=["POST"])
@admin_required
def sync_employees():
    """Re-import PDF, updating changed HR data on existing member-list users."""
    from app.utils.pdf.employee_scraper import scrape_employees

    pdf_path = os.path.join(
        current_app.root_path, "static", "turnusfiler", "ansinitet.pdf"
    )
    if not os.path.exists(pdf_path):
        flash(f"PDF ikke funnet: {pdf_path}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        scraped = scrape_employees(pdf_path)
    except Exception as e:
        flash(f"Feil ved lesing av PDF: {e}", "danger")
        return redirect(url_for("admin.manage_employees"))

    try:
        result = user_service.sync_employees_from_scrape(scraped)
        msg = (
            f"Synkronisering fullført av {len(scraped)} ansatte: "
            f"{result['updated']} oppdatert, {result['unchanged']} uendret."
        )
        if result["merged_by_name"]:
            msg += f" {result['merged_by_name']} koblet til medlemsliste på navn."
        if result["merged_by_date"]:
            msg += f" {result['merged_by_date']} koblet til medlemsliste på ansettelsesdato."
        if result["removed_from_list"]:
            msg += f" {result['removed_from_list']} ikke lenger på lista."
        if result["skipped_unmatched"]:
            msg += (
                f" {result['skipped_unmatched']} ikke funnet på medlemslisten "
                f"— hoppet over."
            )
        flash(msg, "success")
    except Exception as e:
        flash(f"Feil ved synkronisering: {e}", "danger")

    return redirect(url_for("admin.manage_employees"))


@admin.route("/add-employee", methods=["POST"])
@admin_required
def add_employee():
    """Manually create a stub user for an employee not in the member list."""
    medlemsnummer = request.form.get("medlemsnummer", "").strip()
    rullenummer = request.form.get("rullenummer", "").strip() or None
    etternavn = request.form.get("etternavn", "").strip()
    fornavn = request.form.get("fornavn", "").strip()
    stasjoneringssted = request.form.get("stasjoneringssted", "").strip() or None
    ans_dato = request.form.get("ans_dato", "").strip() or None
    fodt_dato = request.form.get("fodt_dato", "").strip() or None
    seniority_nr_raw = request.form.get("seniority_nr", "").strip()
    seniority_nr = int(seniority_nr_raw) if seniority_nr_raw.isdigit() else None

    if not medlemsnummer or not etternavn or not fornavn:
        flash("NLF-medlemsnummer, etternavn og fornavn er påkrevd.", "danger")
        return redirect(url_for("admin.manage_employees"))

    success, message = user_service.create_stub_user(
        etternavn=etternavn,
        fornavn=fornavn,
        medlemsnummer=medlemsnummer,
        rullenummer=rullenummer,
        stasjoneringssted=stasjoneringssted,
        ans_dato=ans_dato,
        fodt_dato=fodt_dato,
        seniority_nr=seniority_nr,
    )
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/cleanup-missing-stubs", methods=["POST"])
@admin_required
def cleanup_missing_stubs():
    """Delete all unregistered stubs absent from the current seniority PDF."""
    success, message, count = user_service.delete_missing_stubs()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/bulk-delete-stubs", methods=["POST"])
@admin_required
def bulk_delete_stubs():
    """Delete the stub users selected from the medlemsliste 'not on list' report."""
    user_ids = [int(uid) for uid in request.form.getlist("user_ids") if uid.isdigit()]
    if not user_ids:
        flash("Ingen brukere valgt.", "danger")
        return redirect(url_for("admin.manage_employees"))
    success, message, count = user_service.delete_stub_users(user_ids)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/reset-to-stub/<int:user_id>", methods=["POST"])
@admin_required
def reset_to_stub(user_id):
    """Reset a registered user back to stub state, keeping their favorites."""
    if user_id == current_user.id:
        flash("Du kan ikke tilbakestille din egen konto.", "danger")
        return redirect(url_for("admin.manage_employees"))
    # Grab the current username before the reset renames it to a stub form,
    # so we can evict its cached User object below.
    target = user_service.get_user_by_id(user_id)
    success, message = user_service.reset_user_to_stub(user_id)
    if success:
        # Evict only the target user's cached pages/flags (targeted so the
        # shared turnus_data_* caches survive). Their selected turnus set isn't
        # reachable from here, so fall back to the active set (the default).
        active = db_utils.get_active_turnus_set()
        ts_id = active["id"] if active else "none"
        cache.delete(df_utils.turnusliste_view_key(user_id, ts_id))
        cache.delete(df_utils.oversikt_view_key(user_id, ts_id))
        cache.delete(f"tour_state_{user_id}")
        cache.delete(f"has_min_turnus_{user_id}")
        if target:
            cache.delete(f"user_{target['username']}")
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/delete-employee/<int:user_id>", methods=["POST"])
@admin_required
def delete_employee(user_id):
    """Delete a stub user. Registered users cannot be deleted via this route."""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            flash("Bruker ikke funnet.", "danger")
            return redirect(url_for("admin.manage_employees"))
        if (user.is_stub or 0) != 1:
            flash("Kun stub-brukere kan slettes via denne siden.", "danger")
            return redirect(url_for("admin.manage_employees"))
    finally:
        db_session.close()

    success, message = db_utils.delete_user(user_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/revert-nlf-review/<int:user_id>", methods=["POST"])
@admin_required
def revert_nlf_review(user_id):
    """Clear the not_on_nlf_list flag, restoring login access for the user."""
    # flag will be re-set by next sync if user is still absent from NLF list
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            flash("Bruker ikke funnet.", "danger")
            return redirect(url_for("admin.manage_employees"))
        user.not_on_nlf_list = 0
        db_session.commit()
        flash("Brukeren er gjenopprettet til normal status.", "success")
    except Exception as e:
        db_session.rollback()
        flash(f"Feil ved gjenoppretting: {e}", "danger")
    finally:
        db_session.close()
    return redirect(url_for("admin.manage_employees"))


@admin.route("/bulk-delete-review", methods=["POST"])
@admin_required
def bulk_delete_review():
    """Delete all flagged stub users (not_on_nlf_list=1, is_stub=1)."""
    db_session = get_db_session()
    try:
        targets = (
            db_session.query(DBUser)
            .filter(DBUser.not_on_nlf_list == 1, DBUser.is_stub == 1)
            .all()
        )
        count = len(targets)
        for u in targets:
            db_session.query(Favorites).filter_by(user_id=u.id).delete()
            db_session.delete(u)
        db_session.commit()
        flash(f"{count} stub-brukere slettet.", "success")
    except Exception as e:
        db_session.rollback()
        flash(f"Feil ved sletting: {e}", "danger")
    finally:
        db_session.close()
    return redirect(url_for("admin.manage_employees"))


@admin.route("/delete-all-stubs", methods=["POST"])
@admin_required
def delete_all_stubs():
    """Delete every stub user regardless of NLF-list status."""
    success, message, _count = user_service.delete_all_stubs()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_employees"))


@admin.route("/export-review-list")
@admin_required
def export_review_list():
    """Export the NLF-review list as a PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    employees = user_service.get_all_stub_users()
    review_list = [emp for emp in employees if emp.get("not_on_nlf_list")]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("Til gjennomgang — ikke på NLF-liste", styles["Heading1"]))
    elements.append(Paragraph(
        f"Generert: {datetime.now().strftime('%d.%m.%Y %H:%M')} — {len(review_list)} brukere",
        styles["Normal"],
    ))
    elements.append(Spacer(1, 6 * mm))

    headers = ["Etternavn", "Fornavn", "Status", "Rullenr.", "NLF-nr.", "Brukernavn", "Ans.dato"]
    rows = [headers]
    for emp in review_list:
        rows.append([
            emp.get("etternavn") or "",
            emp.get("fornavn") or "",
            "Registrert" if emp.get("is_registered") else "Stub",
            emp.get("rullenummer") or "",
            emp.get("medlemsnummer") or "",
            emp.get("username") or "",
            emp.get("ans_dato") or "",
        ])

    col_widths = [45 * mm, 55 * mm, 25 * mm, 22 * mm, 22 * mm, 45 * mm, 25 * mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)
    return send_file(
        buf,
        download_name="gjennomgang_nlf.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )
