from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.forms import CreateUserForm, EditUserForm
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils


@admin.route("/create_user", methods=["GET", "POST"])
@admin_required
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        success, message = db_utils.create_user(
            username=form.username.data,
            password=form.password.data,
            is_auth=1 if form.is_auth.data else 0,
        )
        if success:
            flash(message, "success")
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash(message, "danger")

    return render_template("create_user.html", form=form, page_name="Create User")


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
            rullenummer=form.rullenummer.data,
            password=form.password.data if form.password.data else None,
            is_auth=1 if form.is_auth.data else 0,
        )
        if success:
            flash(message, "success")
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash(message, "danger")
    elif request.method == "GET":
        form.username.data = user["username"]
        # Only pre-fill email if it looks like a real address.
        # Admin accounts created via create_user() have email=username (no @),
        # pre-filling that would cause Email() validator to reject the form.
        email_val = user.get("email") or ""
        form.email.data = email_val if "@" in email_val else ""
        form.rullenummer.data = user.get("rullenummer")
        form.is_auth.data = user["is_auth"] == 1

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

    success, message = db_utils.delete_user(user_id)
    if success:
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
