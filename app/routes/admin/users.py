from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.extensions import cache
from app.forms import EditUserForm
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils


@admin.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user = db_utils.get_user_by_id(user_id)
    if not user:
        flash("Bruker ikke funnet.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    form = EditUserForm()

    if form.validate_on_submit():
        success, message = db_utils.update_user(
            user_id=user_id,
            username=form.username.data,
            email=(form.email.data or "").strip() or None,
            name=(form.name.data or "").strip() or None,
            medlemsnummer=(form.medlemsnummer.data or "").strip() or None,
            rullenummer=(form.rullenummer.data or "").strip() or None,
            stasjoneringssted=(form.stasjoneringssted.data or "").strip() or None,
            ans_dato=(form.ans_dato.data or "").strip() or None,
            fodt_dato=(form.fodt_dato.data or "").strip() or None,
            seniority_nr=form.seniority_nr.data,
            password=form.password.data if form.password.data else None,
            is_auth=1 if form.is_auth.data else 0,
            email_verified=1 if form.email_verified.data else 0,
            is_stub=1 if form.is_stub.data else 0,
        )
        if success:
            # Evict the cached Flask-Login wrapper (60s TTL) so changed
            # username/admin rights take effect immediately.
            cache.delete(f"user_{user['username']}")
            if form.username.data != user["username"]:
                cache.delete(f"user_{form.username.data}")
            flash(message, "success")
            return redirect(url_for("admin.user_detail", user_id=user_id))
        else:
            flash(message, "danger")
    elif request.method == "GET":
        form.username.data = user["username"]
        # Only pre-fill email if it looks like a real address.
        # Admin accounts created via create_user() have email=username (no @),
        # pre-filling that would cause Email() validator to reject the form.
        email_val = user.get("email") or ""
        form.email.data = email_val if "@" in email_val else ""
        form.name.data = user.get("name")
        form.medlemsnummer.data = user.get("medlemsnummer")
        form.rullenummer.data = user.get("rullenummer")
        form.stasjoneringssted.data = user.get("stasjoneringssted")
        form.ans_dato.data = user.get("ans_dato")
        form.fodt_dato.data = user.get("fodt_dato")
        form.seniority_nr.data = user.get("seniority_nr")
        form.is_auth.data = user["is_auth"] == 1
        form.email_verified.data = user.get("email_verified") == 1
        form.is_stub.data = user.get("is_stub") == 1

    return render_template(
        "edit_user.html", form=form, user=user, page_name="Edit User"
    )


@admin.route("/delete_user/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        flash("Du kan ikke slette din egen konto.", "danger")
        return redirect(url_for("admin.manage_employees"))

    user = db_utils.get_user_by_id(user_id)
    success, message = db_utils.delete_user(user_id)
    if success:
        if user:
            cache.delete(f"user_{user['username']}")
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(url_for("admin.manage_employees"))


@admin.route("/toggle_auth/<int:user_id>", methods=["POST"])
@admin_required
def toggle_auth(user_id):
    # Prevent admin from disabling their own auth
    if user_id == current_user.id:
        flash("Du kan ikke deaktivere dine egne rettigheter.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    success, message = db_utils.toggle_user_auth(user_id)
    if success:
        user = db_utils.get_user_by_id(user_id)
        if user:
            cache.delete(f"user_{user['username']}")
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(url_for("admin.admin_dashboard"))


@admin.route("/user/<int:user_id>")
@admin_required
def user_detail(user_id):
    """Show full detail for one user: HR info, account status, and favorites."""
    from datetime import datetime, timezone

    detail = user_service.get_user_detail(user_id)
    if not detail:
        flash("Bruker ikke funnet.", "danger")
        return redirect(url_for("admin.manage_employees"))

    # Compute account age in days
    age_days = None
    created = detail.get("created_at")
    if created:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days

    display_name = detail["name"] or detail["username"]
    return render_template(
        "admin_user_detail.html",
        page_name=f"Brukerdetaljer — {display_name}",
        detail=detail,
        age_days=age_days,
    )
