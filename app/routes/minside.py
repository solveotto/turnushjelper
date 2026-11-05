from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms import ChangePasswordForm
from app.services.innplassering_service import get_innplassering_for_user
from app.services import broadcast_email_service, user_service

minside = Blueprint("minside", __name__, url_prefix="/minside")


@minside.route("/")
@login_required
def user_minside():
    """Display user profile page with password change form"""
    form = ChangePasswordForm()

    # Get user data for display
    user_data = user_service.get_user_data(current_user.username)
    innplassering = get_innplassering_for_user(current_user.id)

    return render_template(
        "minside.html",
        form=form,
        user_data=user_data,
        innplassering=innplassering,
        wants_announcements=not broadcast_email_service.is_opted_out(current_user.id),
        page_name="Min Side",
    )


@minside.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Handle password change form submission"""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        success, message = user_service.update_user_password(
            current_user.id, form.current_password.data, form.new_password.data
        )

        if success:
            flash("Passord oppdatert!", "success")
        else:
            flash(message, "danger")
    else:
        # Handle form validation errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "danger")

    return redirect(url_for("minside.user_minside"))


@minside.route("/kunngjoringer", methods=["POST"])
@login_required
def update_announcements():
    """Turn announcements by email on or off"""
    wants_them = request.form.get("announcements") == "on"
    if broadcast_email_service.set_opt_out(current_user.id, not wants_them):
        flash("Innstillingen er lagret.", "success")
    else:
        flash("Kunne ikke lagre innstillingen.", "danger")
    return redirect(url_for("minside.user_minside"))


def _unsubscribe_link_is_bad():
    return render_template("unsubscribe.html", valid=False), 400


@minside.route("/avmeld/<token>", methods=["GET"])
def unsubscribe(token):
    """The link in every announcement, public so it works logged out. It changes
    nothing, because mail scanners follow links. The button posts."""
    user_id = broadcast_email_service.user_id_from_token(token)
    opted_out = broadcast_email_service.is_opted_out(user_id) if user_id else None
    if opted_out is None:
        return _unsubscribe_link_is_bad()
    return render_template("unsubscribe.html", valid=True, token=token, opted_out=opted_out)


@minside.route("/avmeld/<token>", methods=["POST"])
def unsubscribe_confirm(token):
    user_id = broadcast_email_service.user_id_from_token(token)
    if not user_id or not broadcast_email_service.set_opt_out(user_id, True):
        return _unsubscribe_link_is_bad()
    return redirect(url_for("minside.unsubscribe", token=token))
