import json
import os

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.database import get_db_session
from app.extensions import cache
from app.forms import CreateTurnusSetForm, UploadStreklisteForm
from app.routes.admin import admin
from app.utils import db_utils
from app.utils.pdf import strekliste_generator
from app.utils.pdf.double_shift_scanner import scan_double_shifts
from config import AppConfig


@admin.route("/turnus-sets")
@admin_required
def manage_turnus_sets():
    """Manage turnus sets"""
    turnus_sets = db_utils.get_all_turnus_sets()
    active_set = db_utils.get_active_turnus_set()
    upload_form = UploadStreklisteForm()

    return render_template(
        "admin_turnus_sets.html",
        page_name="Manage Turnus Sets",
        turnus_sets=turnus_sets,
        active_set=active_set,
        upload_form=upload_form,
    )


@admin.route("/create-turnus-set", methods=["GET", "POST"])
@admin_required
def create_turnus_set():
    """Create a new turnus set"""
    form = CreateTurnusSetForm()

    if form.validate_on_submit():
        year_id = (form.year_identifier.data or "").upper()

        # Determine file paths
        if form.use_existing_files.data:
            # Use existing files from turnusfiler directory
            turnusfiler_dir = os.path.join(
                AppConfig.static_dir, "turnusfiler", year_id.lower()
            )
            turnus_json_path = os.path.join(turnusfiler_dir, f"turnus_schedule_{year_id}.json")
            df_json_path = os.path.join(turnusfiler_dir, f"turnus_stats_{year_id}.json")

            # Check if main turnus file exists
            if not os.path.exists(turnus_json_path):
                flash(f"Turnus JSON-fil ikke funnet: {turnus_json_path}", "danger")
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )

            # Validate existing JSON before creating the DB record
            from app.utils.pdf.scraper_validator import validate_turnus_json

            with open(turnus_json_path, "r") as _f:
                import json as _json
                _existing_data = _json.load(_f)
            _valid, _errors = validate_turnus_json(_existing_data)
            if not _valid:
                for err in _errors:
                    flash(f"Valideringsfeil: {err}", "danger")
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )
            flash(
                f"Validering OK: {len(_existing_data)} av {len(_existing_data)} turnuser godkjent.",
                "info",
            )
        else:
            # Handle PDF upload
            if not form.pdf_file.data:
                flash(
                    "Vennligst last opp en PDF-fil eller bruk eksisterende filer.",
                    "danger",
                )
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )

            # PDF upload - scrape it
            turnus_json_path, df_json_path = handle_pdf_upload(
                form.pdf_file.data, year_id
            )
            if not turnus_json_path:
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )

        # Generate statistics if missing
        if not df_json_path or not os.path.exists(df_json_path):
            try:
                from app.utils.shift_stats import Turnus

                stats = Turnus(turnus_json_path)
                df_json_path = os.path.join(
                    AppConfig.static_dir,
                    "turnusfiler",
                    year_id.lower(),
                    f"turnus_stats_{year_id}.json",
                )
                stats.stats_df.to_json(df_json_path)
                flash("Statistikk-JSON generert automatisk.", "info")
            except Exception as e:
                flash(f"Feil ved generering av statistikk: {e}", "danger")
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )

        # Create turnus set in database
        success, message = db_utils.create_turnus_set(
            name=form.name.data,
            year_identifier=year_id,
            is_active=form.is_active.data,
            turnus_file_path=turnus_json_path,
            df_file_path=df_json_path,
        )

        if success:
            # Add shifts to database
            turnus_set = db_utils.get_turnus_set_by_year(year_id)
            if turnus_set:
                db_utils.add_shifts_to_turnus_set(turnus_json_path, turnus_set["id"])
                flash(f"Turnussett {year_id} opprettet!", "success")
            else:
                flash("Turnussett opprettet, men vakter ikke lagt til.", "warning")
            return redirect(url_for("admin.manage_turnus_sets"))
        else:
            flash(message, "danger")

    return render_template(
        "admin_create_turnus_set.html", page_name="Opprett turnussett", form=form
    )


def handle_pdf_upload(pdf_file, year_id):
    """Handle PDF upload and scraping"""
    try:
        from app.utils.pdf.scraper_validator import validate_turnus_json
        from app.utils.pdf.shiftscraper import ShiftScraper

        # Create turnusfiler directory
        turnusfiler_dir = os.path.join(
            AppConfig.static_dir, "turnusfiler", year_id.lower()
        )
        os.makedirs(turnusfiler_dir, exist_ok=True)

        # Save PDF file
        pdf_path = os.path.join(turnusfiler_dir, f"turnuser_{year_id}.pdf")
        pdf_file.save(pdf_path)

        # Scrape PDF into memory
        scraper = ShiftScraper()
        scraper.scrape_pdf(pdf_path, year_id)

        # Validate before writing anything to disk
        valid, errors = validate_turnus_json(scraper.turnuser)
        if not valid:
            os.remove(pdf_path)
            for err in errors:
                flash(f"Valideringsfeil: {err}", "danger")
            return None, None

        # Write JSON only after successful validation
        turnus_json_path = scraper.create_json(year_id=year_id)

        flash(
            f"Validering OK: {len(scraper.turnuser)} av {len(scraper.turnuser)} turnuser godkjent.",
            "info",
        )
        flash("PDF skrapet! JSON-filer opprettet.", "success")
        return turnus_json_path, None  # df_json_path will be generated later

    except Exception as e:
        flash(f"Feil ved skraping av PDF: {e}", "danger")
        return None, None


@admin.route("/switch-turnus-set", methods=["POST"])
@admin_required
def switch_turnus_set():
    """Switch to a different turnus set"""
    turnus_set_id = request.form.get("turnus_set_id", type=int)
    success, message = db_utils.set_active_turnus_set(turnus_set_id)

    if success:
        # Reload the data manager with new active set
        from app.routes.main import df_manager

        df_manager.reload_active_set()
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/refresh-turnus-set/<int:turnus_set_id>", methods=["POST"])
@admin_required
def refresh_turnus_set(turnus_set_id):
    """Re-scrape the PDF and update shift names in the database, preserving favorites."""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        flash("Turnussett ikke funnet.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    year_id = turnus_set["year_identifier"]
    version = year_id.lower()

    try:
        from app.utils.pdf.scraper_validator import validate_turnus_json
        from app.utils.pdf.shiftscraper import ShiftScraper
        from app.utils.shift_stats import Turnus

        # Find the original PDF
        turnusfiler_dir = os.path.join(AppConfig.static_dir, "turnusfiler", version)
        pdf_path = os.path.join(turnusfiler_dir, f"turnuser_{year_id}.pdf")

        if not os.path.exists(pdf_path):
            flash(f"PDF ikke funnet: {pdf_path}", "danger")
            return redirect(url_for("admin.manage_turnus_sets"))

        # Re-scrape the PDF into memory
        scraper = ShiftScraper()
        scraper.scrape_pdf(pdf_path, year_id)

        # Validate before overwriting the existing JSON on disk
        valid, errors = validate_turnus_json(scraper.turnuser)
        if not valid:
            for err in errors:
                flash(f"Valideringsfeil: {err}", "danger")
            flash("Eksisterende turnusdata er ikke endret.", "warning")
            return redirect(url_for("admin.manage_turnus_sets"))

        flash(
            f"Validering OK: {len(scraper.turnuser)} av {len(scraper.turnuser)} turnuser godkjent.",
            "info",
        )
        turnus_json_path = scraper.create_json(year_id=year_id)

        # Regenerate statistics JSON
        stats = Turnus(turnus_json_path)
        df_json_path = os.path.join(turnusfiler_dir, f"turnus_stats_{year_id}.json")
        stats.stats_df.to_json(df_json_path)

        # Update shift names in DB (preserving favorites)
        summary = db_utils.refresh_turnus_set_shifts(turnus_set_id, turnus_json_path)

        # Update file paths in DB
        db_utils.update_turnus_set_paths(turnus_set_id, turnus_json_path, df_json_path)

        # Reload data manager if this is the active set
        active_set = db_utils.get_active_turnus_set()
        if active_set and active_set["id"] == turnus_set_id:
            from app.routes.main import df_manager

            df_manager.reload_active_set()

        # Build summary message
        parts = []
        if summary["renamed"]:
            parts.append(f"{len(summary['renamed'])} omdøpt")
        if summary["added"]:
            parts.append(f"{len(summary['added'])} nye")
        if summary["removed"]:
            parts.append(f"{len(summary['removed'])} fjernet")
        parts.append(f"{len(summary['unchanged'])} uendret")
        flash(f"Turnussett {year_id} oppdatert: {', '.join(parts)}.", "success")

        if summary["renamed"]:
            renamed_details = "; ".join(
                f"{r['old']} → {r['new']}" for r in summary["renamed"][:10]
            )
            if len(summary["renamed"]) > 10:
                renamed_details += f" ... og {len(summary['renamed']) - 10} til"
            flash(f"Omdøpte vakter: {renamed_details}", "info")

    except Exception as e:
        flash(f"Feil ved oppdatering av turnussett: {e}", "danger")

    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/turnusnokkel-status/<int:turnus_set_id>")
@admin_required
def turnusnokkel_status(turnus_set_id):
    """AJAX endpoint: check if turnusnøkkel template exists for a turnus set."""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    version = turnus_set["year_identifier"].lower()
    year_id = turnus_set["year_identifier"]
    template_path = os.path.join(
        AppConfig.turnusfiler_dir, version, f"turnusnøkkel_{year_id}_org.xlsx"
    )
    return jsonify({
        "status": "success",
        "has_template": os.path.exists(template_path),
    })


@admin.route("/upload-turnusnokkel/<int:turnus_set_id>", methods=["POST"])
@admin_required
def upload_turnusnokkel(turnus_set_id):
    """Upload a turnusnøkkel template Excel file for a turnus set."""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        flash("Turnussett ikke funnet.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    uploaded = request.files.get("xlsx_file")
    if not uploaded or not uploaded.filename:
        flash("Ingen fil valgt.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    if not uploaded.filename.lower().endswith((".xlsx", ".xlsm")):
        flash("Kun Excel-filer (.xlsx) er tillatt.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    version = turnus_set["year_identifier"].lower()
    year_id = turnus_set["year_identifier"]
    turnusfiler_dir = os.path.join(AppConfig.turnusfiler_dir, version)
    os.makedirs(turnusfiler_dir, exist_ok=True)

    save_path = os.path.join(turnusfiler_dir, f"turnusnøkkel_{year_id}_org.xlsx")
    uploaded.save(save_path)
    flash(f"Turnusnøkkel mal lastet opp for {year_id}.", "success")
    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/innplassering-status/<int:turnus_set_id>")
@admin_required
def innplassering_status(turnus_set_id):
    """AJAX endpoint: return innplassering record count for a turnus set."""
    from app.models import Innplassering

    db_session = get_db_session()
    try:
        count = db_session.query(Innplassering).filter_by(turnus_set_id=turnus_set_id).count()
    finally:
        db_session.close()

    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    version = turnus_set["year_identifier"].lower()
    pdf_path = os.path.join(
        AppConfig.static_dir, "turnusfiler", version,
        f"innplassering_{turnus_set['year_identifier']}.pdf"
    )
    return jsonify({
        "status": "success",
        "record_count": count,
        "has_pdf": os.path.exists(pdf_path),
    })


@admin.route("/import-innplassering/<int:turnus_set_id>", methods=["POST"])
@admin_required
def import_innplassering_route(turnus_set_id):
    """Upload an Innplassering PDF and import its shift assignments into the DB."""
    from app.services.innplassering_service import import_innplassering

    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        flash("Turnussett ikke funnet.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    year_id = turnus_set["year_identifier"]
    version = year_id.lower()
    turnusfiler_dir = os.path.join(AppConfig.static_dir, "turnusfiler", version)
    os.makedirs(turnusfiler_dir, exist_ok=True)

    pdf_save_path = os.path.join(turnusfiler_dir, f"innplassering_{year_id}.pdf")

    # Accept an uploaded file, or fall back to the previously-saved PDF
    uploaded = request.files.get("pdf_file")
    if uploaded and uploaded.filename:
        if not uploaded.filename.lower().endswith(".pdf"):
            flash("Kun PDF-filer er tillatt.", "danger")
            return redirect(url_for("admin.manage_turnus_sets"))
        uploaded.save(pdf_save_path)
    elif not os.path.exists(pdf_save_path):
        flash(f"Ingen innplassering PDF funnet. Last opp en PDF-fil.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    json_path = turnus_set.get("turnus_file_path")
    if not json_path or not os.path.exists(json_path):
        flash("Turnus JSON-fil ikke funnet for dette turnussettet.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    success, message = import_innplassering(pdf_save_path, turnus_set_id, json_path)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/delete-turnus-set/<int:turnus_set_id>", methods=["POST"])
@admin_required
def delete_turnus_set(turnus_set_id):
    """Delete a turnus set"""
    # Get the turnus set info before deleting (for cleanup)
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    version = turnus_set["year_identifier"].lower() if turnus_set else None

    success, message = db_utils.delete_turnus_set(turnus_set_id)

    if success:
        # Also delete strekliste images if they exist
        if version:
            img_result = strekliste_generator.delete_all_images(version)
            if img_result.get("deleted_count", 0) > 0:
                message += (
                    f" ({img_result['deleted_count']} strekliste images also deleted)"
                )

        # If we deleted the active set, reload the data manager
        from app.routes.main import df_manager

        df_manager.reload_active_set()
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/strekliste-status/<int:turnus_set_id>")
@admin_required
def strekliste_status(turnus_set_id):
    """AJAX endpoint to get strekliste status for a turnus set"""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    version = turnus_set["year_identifier"].lower()
    status = strekliste_generator.get_strekliste_status(version)

    # Include double shift scan info if available
    double_shifts_path = os.path.join(
        AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json"
    )
    if os.path.exists(double_shifts_path):
        try:
            with open(double_shifts_path, "r", encoding="utf-8") as f:
                ds_data = json.load(f)
            status["double_shift_count"] = len(ds_data.get("dobbelt_tur", []))
            status["delt_dagsverk_count"] = len(ds_data.get("delt_dagsverk", []))
        except (json.JSONDecodeError, OSError):
            pass

    return jsonify({"status": "success", "data": status})


@admin.route("/upload-strekliste/<int:turnus_set_id>", methods=["POST"])
@admin_required
def upload_strekliste(turnus_set_id):
    """Upload a strekliste PDF for a turnus set"""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        flash("Turnussett ikke funnet.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))

    form = UploadStreklisteForm()
    if form.validate_on_submit():
        pdf_file = form.pdf_file.data
        version = turnus_set["year_identifier"].lower()

        result = strekliste_generator.save_uploaded_pdf(pdf_file, version)

        if result["success"]:
            flash(
                f"Strekliste PDF lastet opp for {turnus_set['year_identifier']}.",
                "success",
            )
        else:
            flash(f"Kunne ikke laste opp PDF: {result['error']}", "danger")
    else:
        flash("Ugyldig fil. Vennligst last opp en PDF-fil.", "danger")

    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/generate-strekliste/<int:turnus_set_id>", methods=["POST"])
@admin_required
def generate_strekliste(turnus_set_id):
    """Generate PNG images from strekliste PDF"""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    version = turnus_set["year_identifier"].lower()

    # Check if PDF exists
    paths = strekliste_generator.get_paths(version)
    if not paths["pdf_exists"]:
        return jsonify(
            {
                "status": "error",
                "message": "No strekliste PDF found. Please upload one first.",
            }
        ), 400

    # Check if force regenerate is requested
    force = (request.json or {}).get("force", False) if request.is_json else False

    # Generate images
    result = strekliste_generator.generate_all_images(version, force=force)

    if result["success"]:
        error_count = len(result.get("errors", []))
        message = f"Generated {len(result['generated'])} images"
        if error_count > 0:
            message += f" ({error_count} errors)"

        # Run double_shift_scanner after successful image generation
        double_shift_data = {}
        double_shift_error = None
        try:
            double_shift_data = scan_double_shifts(paths["pdf_path"])

            double_shift_output = os.path.join(
                AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json"
            )
            with open(double_shift_output, "w", encoding="utf-8") as f:
                json.dump(double_shift_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            double_shift_error = str(e)

        response = {
            "status": "success",
            "message": message,
            "generated": len(result["generated"]),
            "skipped": len(result["skipped"]),
            "errors": error_count,
            "error_details": result.get("errors", [])[:10],
            "total": result["total"],
            "double_shift_count": len(double_shift_data.get("dobbelt_tur", [])),
            "delt_shift_count": len(double_shift_data.get("delt_dagsverk", [])),
        }
        if double_shift_error:
            response["double_shift_error"] = double_shift_error

        return jsonify(response)
    else:
        return jsonify(
            {"status": "error", "message": result.get("error", "Unknown error")}
        ), 500


@admin.route("/delete-strekliste-images/<int:turnus_set_id>", methods=["POST"])
@admin_required
def delete_strekliste_images(turnus_set_id):
    """Delete all generated strekliste images for a turnus set"""
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    version = turnus_set["year_identifier"].lower()
    result = strekliste_generator.delete_all_images(version)

    if result["success"]:
        return jsonify(
            {
                "status": "success",
                "message": f"Deleted {result['deleted_count']} images",
                "deleted_count": result["deleted_count"],
            }
        )
    else:
        return jsonify(
            {"status": "error", "message": result.get("error", "Unknown error")}
        ), 500
