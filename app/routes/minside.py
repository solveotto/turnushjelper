from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.forms import ChangePasswordForm
from app.services.innplassering_service import get_innplassering_for_user
from app.utils import db_utils

minside = Blueprint("minside", __name__, url_prefix="/minside")


@minside.route("/")
@login_required
def user_minside():
    """Display user profile page with password change form"""
    form = ChangePasswordForm()

    # Get user data for display
    user_data = db_utils.get_user_data(current_user.username)
    innplassering = get_innplassering_for_user(current_user.id)

    return render_template(
        "minside.html", form=form, user_data=user_data, innplassering=innplassering, page_name="Min Side"
    )


@minside.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Handle password change form submission"""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        success, message = db_utils.update_user_password(
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
