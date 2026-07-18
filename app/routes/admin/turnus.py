import json
import logging
import os

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.database import get_db_session
from app.extensions import cache
from app.forms import CreateTurnusSetForm, UploadStreklisteForm
from app.routes.admin import admin
from app.utils import db_utils, df_utils, protected_paths
from app.utils.pdf import strekliste_generator
from app.utils.pdf.double_shift_scanner import scan_double_shifts
from config import AppConfig

# Dedicated audit logger (handler configured in app/routes/main.py).
ingest_logger = logging.getLogger("turnus.ingest")


def _current_username():
    return getattr(current_user, "username", "?")


def _flash_validation_errors(errors, year_id):
    """Flash a summarized validation failure and record the full list to the log."""
    n = len(errors)
    flash(f"Validering feilet: {n} problem(er) i turnussett {year_id}.", "danger")
    for err in errors[:10]:
        flash(err, "danger")
    if n > 10:
        flash(f"... og {n - 10} til (se turnus_import.log for full liste).", "danger")
    ingest_logger.warning(
        "Turnus import FAILED %s (user=%s): %d problem(s): %s",
        year_id, _current_username(), n, " | ".join(errors),
    )


def _log_ingest_success(year_id, count):
    ingest_logger.info(
        "Turnus import OK %s (user=%s): %d turnuser validated",
        year_id, _current_username(), count,
    )


@admin.route("/turnus-sets")
@admin_required
def manage_turnus_sets():
    """Manage turnus sets"""
    from app.services import import_turnusset_service

    turnus_sets = db_utils.get_all_turnus_sets()
    active_set = db_utils.get_active_turnus_set()
    upload_form = UploadStreklisteForm()

    return render_template(
        "admin_turnus_sets.html",
        page_name="Manage Turnus Sets",
        turnus_sets=turnus_sets,
        active_set=active_set,
        upload_form=upload_form,
        pending_imports=import_turnusset_service.list_pending_imports(),
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
                _flash_validation_errors(_errors, year_id)
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )
            _log_ingest_success(year_id, len(_existing_data))
            flash(
                f"Validering OK: {len(_existing_data)} av {len(_existing_data)} turnuser godkjent.",
                "info",
            )
        else:
            # Handle schedule upload (timeskjema or PDF, sniffed by content)
            from app.utils.timeskjema_parser import sniff_format

            schedule_file = form.schedule_file.data
            if not schedule_file:
                flash(
                    "Vennligst last opp en turnusfil eller bruk eksisterende filer.",
                    "danger",
                )
                return render_template(
                    "admin_create_turnus_set.html",
                    page_name="Opprett turnussett",
                    form=form,
                )

            file_bytes = schedule_file.read()
            schedule_file.seek(0)
            file_format = sniff_format(file_bytes)

            if file_format == "timeskjema":
                return _handle_timeskjema_create(form, year_id, file_bytes)
            if file_format == "pdf":
                turnus_json_path, df_json_path = handle_pdf_upload(
                    schedule_file, year_id
                )
                if not turnus_json_path:
                    return render_template(
                        "admin_create_turnus_set.html",
                        page_name="Opprett turnussett",
                        form=form,
                    )
            else:
                flash(
                    "Ukjent filformat: filen er verken et timeskjema-eksport "
                    "eller en PDF. Import avvist.",
                    "danger",
                )
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
            AppConfig.static_dir, "turnusfiler", year_id.lower(), "pdf"
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
            _flash_validation_errors(errors, year_id)
            return None, None

        # Write JSON only after successful validation
        turnus_json_path = scraper.create_json(year_id=year_id)

        _log_ingest_success(year_id, len(scraper.turnuser))
        flash(
            f"Validering OK: {len(scraper.turnuser)} av {len(scraper.turnuser)} turnuser godkjent.",
            "info",
        )
        flash("PDF skrapet! JSON-filer opprettet.", "success")
        return turnus_json_path, None  # df_json_path will be generated later

    except Exception as e:
        ingest_logger.exception(
            "Turnus import CRASHED %s (user=%s)", year_id, _current_username()
        )
        flash(f"Feil ved skraping av PDF: {e}", "danger")
        return None, None


def _handle_timeskjema_create(form, year_id, file_bytes):
    """Timeskjema import: parse, self-check, validate; optionally cross-verify
    against a PDF. Diffs stage for approval; otherwise finalize directly."""
    import tempfile

    from app.services import import_turnusset_service
    from app.utils.pdf.scraper_validator import validate_turnus_json
    from app.utils.timeskjema_parser import TimeskjemaParseError, parse_timeskjema
    from app.utils.turnus_diff import diff_turnus_data, enrich_dagsverk

    def render_form():
        return render_template(
            "admin_create_turnus_set.html", page_name="Opprett turnussett", form=form
        )

    try:
        result = parse_timeskjema(file_bytes)
    except TimeskjemaParseError as e:
        _flash_validation_errors(e.errors, year_id)
        return render_form()

    warning = result.year_id_warning(year_id)
    if warning:
        flash(warning, "warning")

    turnuser = result.turnuser
    valid, errors = validate_turnus_json(turnuser)
    if not valid:
        _flash_validation_errors(errors, year_id)
        return render_form()

    diff = None
    pdf_bytes = None
    if form.verify_pdf_file.data:
        from app.utils.pdf.shiftscraper import ShiftScraper

        pdf_bytes = form.verify_pdf_file.data.read()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                scraper = ShiftScraper()
                scraper.scrape_pdf(tmp.name, year_id)
        except Exception as e:
            ingest_logger.exception(
                "Turnus verify-PDF scrape CRASHED %s (user=%s)",
                year_id, _current_username(),
            )
            flash(
                f"Verifiserings-PDF kunne ikke leses ({e}). Importen er avvist — "
                "last opp på nytt uten verifiserings-PDF for å importere uten kontroll.",
                "danger",
            )
            return render_form()
        diff = diff_turnus_data(turnuser, scraper.turnuser)
        turnuser = enrich_dagsverk(turnuser, scraper.turnuser)

    _log_ingest_success(year_id, len(turnuser))
    flash(
        f"Validering OK: {len(turnuser)} av {len(turnuser)} turnuser godkjent.",
        "info",
    )

    meta = {
        "name": form.name.data,
        "year_identifier": year_id,
        "is_active": bool(form.is_active.data),
        "uploader": _current_username(),
    }
    import_turnusset_service.stage_pending_import(
        year_id, turnuser, diff or {"is_empty": True}, meta, file_bytes, pdf_bytes
    )

    if diff is not None and not diff["is_empty"]:
        n_cells = len(diff["cells"]) + len(diff["totals"])
        flash(
            f"PDF-verifisering fant {n_cells} avvik. Se gjennom og godkjenn "
            "eller avbryt importen.",
            "warning",
        )
        return redirect(url_for("admin.import_turnusset_review", year_id=year_id))

    if diff is not None:
        flash("PDF-verifisering: ingen avvik.", "info")

    success, message = import_turnusset_service.finalize_turnusset_import(
        year_id, meta["name"], meta["is_active"], turnuser
    )
    if not success:
        import_turnusset_service.clear_pending_import(year_id)
        flash(message, "danger")
        return render_form()
    flash(message, "success")
    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/import-turnusset/review/<year_id>")
@admin_required
def import_turnusset_review(year_id):
    """Review page for a staged timeskjema import with PDF differences."""
    from app.services import import_turnusset_service

    if not import_turnusset_service.is_valid_year_id(year_id):
        flash("Ugyldig årsidentifikator.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))
    staged = import_turnusset_service.load_pending_import(year_id)
    if staged is None:
        flash(f"Ingen ventende import for {year_id}.", "warning")
        return redirect(url_for("admin.manage_turnus_sets"))
    return render_template(
        "admin_import_review.html",
        page_name="Godkjenn turnusimport",
        year_id=year_id.upper(),
        diff=staged["diff"],
        meta=staged["meta"],
        turnus_count=len(staged["turnuser"]),
    )


@admin.route("/import-turnusset/approve/<year_id>", methods=["POST"])
@admin_required
def import_turnusset_approve(year_id):
    """Finalize a staged import after admin adjudication of the diff."""
    from app.services import import_turnusset_service

    if not import_turnusset_service.is_valid_year_id(year_id):
        flash("Ugyldig årsidentifikator.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))
    staged = import_turnusset_service.load_pending_import(year_id)
    if staged is None:
        flash(f"Ingen ventende import for {year_id}.", "warning")
        return redirect(url_for("admin.manage_turnus_sets"))

    meta = staged["meta"]
    success, message = import_turnusset_service.finalize_turnusset_import(
        year_id, meta["name"], meta["is_active"], staged["turnuser"]
    )
    if success:
        ingest_logger.info(
            "Turnus import APPROVED %s (user=%s, staged by %s)",
            year_id, _current_username(), meta.get("uploader", "?"),
        )
        flash(message, "success")
    else:
        flash(message, "danger")
    return redirect(url_for("admin.manage_turnus_sets"))


@admin.route("/import-turnusset/cancel/<year_id>", methods=["POST"])
@admin_required
def import_turnusset_cancel(year_id):
    """Discard a staged import."""
    from app.services import import_turnusset_service

    if not import_turnusset_service.is_valid_year_id(year_id):
        flash("Ugyldig årsidentifikator.", "danger")
        return redirect(url_for("admin.manage_turnus_sets"))
    import_turnusset_service.clear_pending_import(year_id)
    ingest_logger.info(
        "Turnus import CANCELLED %s (user=%s)", year_id, _current_username()
    )
    flash(f"Import av {year_id.upper()} avbrutt. Ingen data er endret.", "info")
    return redirect(url_for("admin.manage_turnus_sets"))


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
    """Re-ingest the stored source file (timeskjema preferred, PDF fallback)
    and update shift names in the database, preserving favorites."""
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
        from app.utils.timeskjema_parser import TimeskjemaParseError, parse_timeskjema
        from app.utils.turnus_diff import enrich_dagsverk

        version_dir = os.path.join(AppConfig.static_dir, "turnusfiler", version)
        timeskjema_path = os.path.join(version_dir, f"turnuser_{year_id}.xls")
        pdf_path = os.path.join(version_dir, "pdf", f"turnuser_{year_id}.pdf")

        if os.path.exists(timeskjema_path):
            # Primary source. Deliberately no diff step here: the stored PDF
            # may be an older revision, and re-surfacing the same known diff on
            # every refresh helps no one. Enrichment, by contrast, is safe to
            # re-run (non-matching base numbers never enrich) and without it a
            # refresh would strip the dagsverk suffixes.
            try:
                result = parse_timeskjema(timeskjema_path)
            except TimeskjemaParseError as e:
                _flash_validation_errors(e.errors, year_id)
                flash("Eksisterende turnusdata er ikke endret.", "warning")
                return redirect(url_for("admin.manage_turnus_sets"))

            turnuser = result.turnuser
            valid, errors = validate_turnus_json(turnuser)
            if not valid:
                _flash_validation_errors(errors, year_id)
                flash("Eksisterende turnusdata er ikke endret.", "warning")
                return redirect(url_for("admin.manage_turnus_sets"))

            if os.path.exists(pdf_path):
                try:
                    scraper = ShiftScraper()
                    scraper.scrape_pdf(pdf_path, year_id)
                    turnuser = enrich_dagsverk(turnuser, scraper.turnuser)
                except Exception:
                    ingest_logger.exception(
                        "Turnus refresh enrichment failed %s (user=%s)",
                        year_id, _current_username(),
                    )
                    flash(
                        "Kunne ikke lese lagret PDF for dagsverk-berikelse; "
                        "oppdaterer med rene vaktnumre.",
                        "warning",
                    )

            count = len(turnuser)
            turnus_json_path = os.path.join(
                version_dir, f"turnus_schedule_{year_id}.json"
            )
            with open(turnus_json_path, "w") as f:
                json.dump(turnuser, f, indent=4)
        elif os.path.exists(pdf_path):
            # Fallback: re-scrape the PDF into memory
            scraper = ShiftScraper()
            scraper.scrape_pdf(pdf_path, year_id)

            # Validate before overwriting the existing JSON on disk
            valid, errors = validate_turnus_json(scraper.turnuser)
            if not valid:
                _flash_validation_errors(errors, year_id)
                flash("Eksisterende turnusdata er ikke endret.", "warning")
                return redirect(url_for("admin.manage_turnus_sets"))

            count = len(scraper.turnuser)
            turnus_json_path = scraper.create_json(year_id=year_id)
        else:
            flash(
                f"Fant verken timeskjema ({timeskjema_path}) eller PDF ({pdf_path}).",
                "danger",
            )
            return redirect(url_for("admin.manage_turnus_sets"))

        _log_ingest_success(year_id, count)
        flash(
            f"Validering OK: {count} av {count} turnuser godkjent.",
            "info",
        )

        # Regenerate statistics JSON
        stats = Turnus(turnus_json_path)
        df_json_path = os.path.join(version_dir, f"turnus_stats_{year_id}.json")
        stats.stats_df.to_json(df_json_path)

        # Counts are derived from the schedule data; drop the stale cache entry
        cache.delete(f"kompdager_{turnus_set_id}")

        # Update shift names in DB (preserving favorites)
        summary = db_utils.refresh_turnus_set_shifts(turnus_set_id, turnus_json_path)

        # Warn (don't block) if the turnus count changed vs the previous version.
        # A legitimate rutetermin can add/remove turnuser, but a silent drop from a
        # misread PDF looks identical to each surviving turnus, so surface it.
        prev_count = len(summary["unchanged"]) + len(summary["renamed"]) + len(summary["removed"])
        new_count = len(summary["unchanged"]) + len(summary["renamed"]) + len(summary["added"])
        if new_count != prev_count:
            flash(
                f"Advarsel: antall turnuser endret fra {prev_count} til {new_count} "
                f"— bekreft at dette er forventet.",
                "warning",
            )
            ingest_logger.warning(
                "Turnus refresh COUNT CHANGED %s (user=%s): %d -> %d turnuser",
                year_id, _current_username(), prev_count, new_count,
            )

        # Update file paths in DB
        db_utils.update_turnus_set_paths(turnus_set_id, turnus_json_path, df_json_path)

        # Drop cached turnus data / kompdag counts so the re-scraped files are
        # served immediately instead of after the 1 h cache timeout.
        df_utils.invalidate_turnus_cache(turnus_set_id)

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
        ingest_logger.exception(
            "Turnus refresh CRASHED %s (user=%s)", year_id, _current_username()
        )
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
    # Kompdag counts are derived from this template — drop the cached counts
    cache.delete(f"kompdager_{turnus_set_id}")
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

    pdf_path = protected_paths.innplassering_pdf_path(turnus_set["year_identifier"])
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
    pdf_save_path = protected_paths.ensure_parent_dir(
        protected_paths.innplassering_pdf_path(year_id)
    )

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
        df_utils.invalidate_turnus_cache(turnus_set_id)
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

            # Double-shift flags are baked into the cached turnus data at
            # load time — drop the cache so the new flags take effect now.
            df_utils.invalidate_turnus_cache(turnus_set_id)
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
