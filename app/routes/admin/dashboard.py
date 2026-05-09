import os

from flask import current_app, flash, redirect, render_template, url_for
from flask_login import current_user

from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.models import DBUser
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils


@admin.route("/dashboard")
@admin_required
def admin_dashboard():
    employees = user_service.get_all_stub_users()
    registered_count = sum(1 for e in employees if e["is_registered"])
    pending_count = sum(1 for e in employees if e["is_stub"] == 1)

    turnus_sets = db_utils.get_all_turnus_sets()
    active_set = db_utils.get_active_turnus_set()

    pdf_path = os.path.join(current_app.root_path, "static", "turnusfiler", "ansinitet.pdf")
    pdf_exists = os.path.exists(pdf_path)

    return render_template(
        "admin.html",
        total_users=len(employees),
        registered_count=registered_count,
        pending_count=pending_count,
        turnus_sets=turnus_sets,
        active_set=active_set,
        pdf_exists=pdf_exists,
        page_name="Admin Panel",
    )


@admin.route("/activity")
@admin_required
def activity_log():
    from app.services.activity_service import get_recent_activity, get_user_stats

    return render_template(
        "admin/activity.html",
        events=get_recent_activity(limit=200),
        user_stats=get_user_stats(),
        page_name="Aktivitetslogg",
    )


@admin.route("/reset-tour", methods=["POST"])
@admin_required
def reset_tour():
    """Reset the guided tour flag for all users so the tour auto-starts again."""
    db_session = get_db_session()
    try:
        db_session.query(DBUser).update({
            DBUser.has_seen_turnusliste_tour: 0,
            DBUser.has_seen_favorites_tour: 0,
            DBUser.has_seen_mintur_tour: 0,
            DBUser.has_seen_compare_tour: 0,
            DBUser.has_seen_welcome: 0,
            DBUser.has_seen_soknadsskjema_tour: 0,
        })
        db_session.commit()
        cache.clear()  # evict all cached pages so data-tour-seen is re-rendered fresh
        flash("Omvisningen er tilbakestilt for alle brukere.", "success")
    except Exception as e:
        db_session.rollback()
        flash(f"Feil ved tilbakestilling: {e}", "danger")
    finally:
        db_session.close()
    return redirect(url_for("admin.admin_dashboard"))


@admin.route("/create-test-user", methods=["POST"])
@admin_required
def create_test_user():
    """Dev tool: create or reset testbruker with random favorites per TurnusSet."""
    success, message = user_service.create_test_user_with_favorites()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.admin_dashboard"))
