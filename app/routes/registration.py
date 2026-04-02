import secrets

from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user
from flask_login import login_user as flask_login_user

from app.extensions import cache, limiter
from app.forms import RegisterForm, ResendVerificationForm
from app.models import User
from app.services import user_service
from app.utils import db_utils, email_utils

registration = Blueprint("registration", __name__)


@registration.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    """Self-registration for users with a pre-seeded stub account."""
    if current_user.is_authenticated:
        return redirect(url_for("shifts.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = (form.email.data or "").lower()
        username = (form.username.data or "").strip()
        rullenummer = (form.rullenummer.data or "").strip()

        # Check if rullenummer exists as an unactivated stub
        stub = user_service.get_user_by_rullenummer(rullenummer)
        if not stub or stub["is_stub"] != 1:
            flash(
                "Dette rullenummeret er ikke autorisert. Kontakt en administrator.",
                "danger",
            )
            return render_template("register.html", form=form)

        # Check if email already registered
        if db_utils.get_user_by_email(email):
            flash("En konto med denne e-postadressen finnes allerede.", "warning")
            return redirect(url_for("auth.login"))

        # Check if username already taken
        if db_utils.get_user_by_username(username):
            flash(
                "Dette brukernavnet er allerede tatt. Vennligst velg et annet.",
                "warning",
            )
            return render_template("register.html", form=form)

        # Activate the stub user with real credentials
        success, message, user_id = user_service.activate_stub_user(
            user_id=stub["id"],
            username=username,
            email=email,
            password=form.password.data,
        )

        if success:
            # Generate and send verification token
            token = secrets.token_urlsafe(32)
            db_utils.create_verification_token(user_id, token)
            email_utils.send_verification_email(email, token)

            return render_template("register.html", form=form, show_success_modal=True)
        else:
            flash(message, "danger")

    return render_template("register.html", form=form)


@registration.route("/verify/<token>")
def verify_email(token):
    """Verify email with token from email link"""
    result = db_utils.verify_token(token)

    if result["success"]:
        # Send welcome email
        if "email" in result:
            email_utils.send_welcome_email(result["email"])

        # Auto-login the user so they don't hit the login page twice
        user_data = db_utils.get_user_by_email(result["email"])
        if user_data:
            user = User(user_data["username"], user_data["id"], user_data["is_auth"])
            flask_login_user(user)
            session['has_seen_tour'] = 0
            session['has_seen_favorites_tour'] = 0
            cache.clear()  # evict any stale cached pages from a previous user with the same ID
            flash("E-post verifisert! Du er nå logget inn.", "success")
            return redirect(url_for("shifts.index"))

        flash("E-post verifisert! Du kan nå logge inn.", "success")
        return redirect(url_for("auth.login"))
    else:
        flash(result["message"], "danger")
        return redirect(url_for("registration.register"))


@registration.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    """Resend verification email for unverified users"""
    form = ResendVerificationForm()
    if form.validate_on_submit():
        email = (form.email.data or "").lower()
        user = db_utils.get_user_by_email(email)

        if user and not user["email_verified"]:
            # Rate limiting check
            if db_utils.can_send_verification_email(user["id"]):
                token = secrets.token_urlsafe(32)
                db_utils.create_verification_token(user["id"], token)
                email_utils.send_verification_email(email, token)
                flash(
                    "Verifiserings-e-post sendt på nytt. Sjekk innboksen din.",
                    "success",
                )
            else:
                flash(
                    "For mange verifiserings-e-poster sendt. Vennligst prøv igjen senere.",
                    "warning",
                )
        else:
            flash("E-post ikke funnet eller allerede verifisert.", "info")

        return redirect(url_for("auth.login"))

    return render_template("resend_verification.html", form=form)
