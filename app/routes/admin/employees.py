import os

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.models import DBUser
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils


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
        if not emp.get("rullenummer"):
            # No rullenummer → admin / system account
            system_list.append(emp)
        elif emp.get("seniority_nr"):
            # Has seniority_nr → matched to current PDF
            if emp.get("is_registered"):
                registered_list.append(emp)
            else:
                stub_list.append(emp)
        else:
            # Has rullenummer but no seniority_nr → not on current PDF
            not_on_list.append(emp)

    pdf_path = os.path.join(
        current_app.root_path, "static", "turnusfiler", "ansinitet.pdf"
    )
    pdf_exists = os.path.exists(pdf_path)

    pdf_date = None
    if pdf_exists:
        from app.utils.pdf.employee_scraper import scrape_pdf_date
        pdf_date = scrape_pdf_date(pdf_path)

    return render_template(
        "admin_employees.html",
        page_name="Ansattliste",
        registered_list=registered_list,
        stub_list=stub_list,
        not_on_list=not_on_list,
        system_list=system_list,
        pdf_exists=pdf_exists,
        pdf_date=pdf_date,
    )


@admin.route("/import-employees", methods=["POST"])
@admin_required
def import_employees():
    """Import employees from the seniority PDF into the stub-user table."""
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

    imported = 0
    skipped = 0
    for emp in scraped:
        if not emp.get("rullenummer"):
            skipped += 1
            continue
        success, _msg = user_service.create_stub_user(
            rullenummer=emp["rullenummer"],
            etternavn=emp["etternavn"],
            fornavn=emp["fornavn"],
            stasjoneringssted=emp.get("stasjoneringssted"),
            ans_dato=emp.get("ans_dato"),
            fodt_dato=emp.get("fodt_dato"),
            seniority_nr=emp.get("seniority_nr"),
        )
        if success:
            imported += 1
        else:
            skipped += 1

    flash(
        f"Importert {imported} nye, hoppet over {skipped} eksisterende av {len(scraped)} totalt.",
        "success",
    )
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
            f"{result['added']} nye, {result['updated']} oppdatert, "
            f"{result['unchanged']} uendret."
        )
        if result["removed_from_list"]:
            msg += f" {result['removed_from_list']} ikke lenger på lista."
        flash(msg, "success")
    except Exception as e:
        flash(f"PDF lagret, men feil ved synkronisering: {e}", "danger")

    return redirect(url_for("admin.manage_employees"))


@admin.route("/sync-employees", methods=["POST"])
@admin_required
def sync_employees():
    """Re-import PDF, adding new stubs and updating changed HR data on existing users."""
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
            f"{result['added']} nye, {result['updated']} oppdatert, "
            f"{result['unchanged']} uendret."
        )
        if result["removed_from_list"]:
            msg += f" {result['removed_from_list']} ikke lenger på lista."
        flash(msg, "success")
    except Exception as e:
        flash(f"Feil ved synkronisering: {e}", "danger")

    return redirect(url_for("admin.manage_employees"))


@admin.route("/add-employee", methods=["POST"])
@admin_required
def add_employee():
    """Manually create a stub user for an employee not in the PDF."""
    rullenummer = request.form.get("rullenummer", "").strip()
    etternavn = request.form.get("etternavn", "").strip()
    fornavn = request.form.get("fornavn", "").strip()
    stasjoneringssted = request.form.get("stasjoneringssted", "").strip() or None
    ans_dato = request.form.get("ans_dato", "").strip() or None
    fodt_dato = request.form.get("fodt_dato", "").strip() or None
    seniority_nr_raw = request.form.get("seniority_nr", "").strip()
    seniority_nr = int(seniority_nr_raw) if seniority_nr_raw.isdigit() else None

    if not rullenummer or not etternavn or not fornavn:
        flash("Rullenummer, etternavn og fornavn er påkrevd.", "danger")
        return redirect(url_for("admin.manage_employees"))

    success, message = user_service.create_stub_user(
        rullenummer=rullenummer,
        etternavn=etternavn,
        fornavn=fornavn,
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


@admin.route("/reset-to-stub/<int:user_id>", methods=["POST"])
@admin_required
def reset_to_stub(user_id):
    """Reset a registered user back to stub state, keeping their favorites."""
    if user_id == current_user.id:
        flash("Du kan ikke tilbakestille din egen konto.", "danger")
        return redirect(url_for("admin.manage_employees"))
    success, message = user_service.reset_user_to_stub(user_id)
    if success:
        cache.clear()  # evict stale data-tour-seen from this user's cached pages
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
