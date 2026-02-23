import logging
import secrets

from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user
from flask_login import login_user as flask_login_user

from app.forms import ForgotPasswordForm, LoginForm, ResetPasswordForm
from app.models import User
from app.utils import db_utils
from app.utils.email_utils import send_password_reset_email

logger = logging.getLogger(__name__)

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
    # from app.routes.main import current_user  # Import here to avoid circular imports

    if current_user.is_authenticated:
        return redirect(url_for("shifts.index"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            db_user_data = db_utils.get_user_data(form.username.data)
            if db_user_data and User.verify_password(
                db_user_data["password"], form.password.data
            ):
                # Stub users have no usable credentials, but guard anyway
                if db_user_data.get("is_stub") == 1:
                    flash(
                        "Kontoen er ikke aktivert ennå. Registrer deg først.",
                        "warning",
                    )
                    return render_template("login.html", form=form)

                # Check email verification status
                if db_user_data.get("email_verified") == 0:
                    flash(
                        "Vennligst bekreft e-posten din før du logger inn. Sjekk innboksen din for verifiseringslenken.",
                        "warning",
                    )
                    return render_template("login.html", form=form)

                user = User(
                    form.username.data, db_user_data["id"], db_user_data["is_auth"]
                )
                flask_login_user(user)

                # Clear any previous turnus set choice for fresh start
                session.pop("user_selected_turnus_set", None)

                return redirect(url_for("shifts.index"))
            else:
                flash(
                    "Innlogging mislyktes. Vennligst sjekk brukernavn og passord",
                    "danger",
                )
        except Exception as e:
            logger.error("Login error: %s", e)
    else:
        if form.errors:
            logger.warning("Login form validation errors: %s", form.errors)

    return render_template("login.html", form=form)


@auth.route("/logout")
@login_required
def logout():
    # Clear turnus set choice on logout
    session.pop("user_selected_turnus_set", None)
    logout_user()
    return render_template("logout.html")


@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("shifts.index"))

    form = ForgotPasswordForm()
    show_success_modal = False

    if form.validate_on_submit():
        email = (form.email.data or "").lower()

        # Check rate limiting
        if not db_utils.can_send_password_reset_email(email):
            flash(
                "En tilbakestillings-e-post ble nylig sendt. Vennligst sjekk innboksen din eller prøv igjen senere.",
                "warning",
            )
            return render_template(
                "forgot_password.html", form=form, show_success_modal=False
            )

        # Get user by email
        user = db_utils.get_user_by_email(email)

        if user:
            # Generate token and create reset record
            token = secrets.token_urlsafe(32)
            success, _msg = db_utils.create_password_reset_token(user["id"], token)
            if success:
                # Send reset email
                if send_password_reset_email(email, token):
                    pass  # Email sent successfully
                else:
                    # Log error but show generic message
                    logger.error("Failed to send password reset email to %s", email)

        # Always show success modal to prevent email enumeration
        show_success_modal = True

    return render_template(
        "forgot_password.html", form=form, show_success_modal=show_success_modal
    )


@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("shifts.index"))

    # Verify token is valid
    token_result = db_utils.verify_password_reset_token(token)

    if not token_result["success"]:
        flash(token_result["message"], "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Update password
        success, message = db_utils.reset_user_password(
            token_result["user_id"], form.password.data
        )

        if success:
            flash("Passordet ditt er tilbakestilt. Du kan nå logge inn.", "success")
            return redirect(url_for("auth.login", email=token_result.get("email", "")))
        else:
            flash(f"Feil ved tilbakestilling av passord: {message}", "danger")

    return render_template("reset_password.html", form=form, token=token)
