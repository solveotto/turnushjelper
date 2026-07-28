import logging
import os
import tempfile
from datetime import date

from flask import flash, render_template, request, send_file
from flask_login import current_user, login_required

from app.database import get_db_session
from app.models import DBUser, SoknadsskjemaChoice
from app.routes.shifts import shifts
from app.utils import db_utils
from app.utils.soknadsskjema_gen import (
    build_soknadsskjema_doc,
    build_soknadsskjema_pdf,
)
from app.utils.turnus_helpers import get_user_turnus_set

logger = logging.getLogger(__name__)


def _get_soknadsskjema_choices(user_id, turnus_set_id):
    """Return {shift_title: {linje_135, linje_246, h_dag, linjeprioritering}} from DB."""
    db_session = get_db_session()
    try:
        rows = (
            db_session.query(SoknadsskjemaChoice)
            .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
            .all()
        )
        return {
            r.shift_title: {
                "linje_135": bool(r.linje_135),
                "linje_246": bool(r.linje_246),
                "h_dag": bool(r.h_dag),
                "linjeprioritering": r.linjeprioritering or "",
            }
            for r in rows
        }
    except Exception as e:
        logger.error("_get_soknadsskjema_choices error: %s", e)
        return {}
    finally:
        db_session.close()


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

    choices = (
        _get_soknadsskjema_choices(user_id, turnus_set_id) if turnus_set_id else {}
    )

    if request.method == "POST":
        dato = request.form.get("dato", "")
        rullenr_og_navn = request.form.get("rullenr_og_navn", "")
        stasjoneringssted = request.form.get("stasjoneringssted", "")
        kommentarer = request.form.get("kommentarer", "")
        fmt = request.form.get("format", "docx")

        year_id = user_turnus_set["year_identifier"] if user_turnus_set else "turnus"

        try:
            if fmt == "pdf":
                pdf_buf = build_soknadsskjema_pdf(
                    dato,
                    rullenr_og_navn,
                    stasjoneringssted,
                    kommentarer,
                    fav_order_lst,
                    choices=choices,
                )
                return send_file(
                    pdf_buf,
                    as_attachment=True,
                    download_name=f"soknadsskjema_{year_id}.pdf",
                    mimetype="application/pdf",
                )
            else:
                doc = build_soknadsskjema_doc(
                    dato,
                    rullenr_og_navn,
                    stasjoneringssted,
                    kommentarer,
                    fav_order_lst,
                    choices=choices,
                )
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
            logger.error("Error generating soknadsskjema (%s): %s", fmt, e)
            flash("Feil ved generering av søknadsskjema. Prøv igjen.", "danger")

    # GET (and POST error fallback)
    if "," in user_name:
        parts = user_name.split(",", 1)
        user_name = f"{parts[1].strip()} {parts[0].strip()}"
    default_rullenr_navn = f"Rullenr.: {user_rullenummer} - {user_name}".strip()
    return render_template(
        "søknadsskjema.html",
        page_name="Søknadsskjema",
        favorites=fav_order_lst,
        choices=choices,
        current_turnus_set=user_turnus_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
        today=date.today().strftime("%d.%m.%Y"),
        today_iso=date.today().strftime("%Y-%m-%d"),
        default_rullenr_navn=default_rullenr_navn,
        default_stasjoneringssted=user_stasjoneringssted,
    )
