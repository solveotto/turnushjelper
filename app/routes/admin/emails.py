from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.routes.admin import admin
from app.utils import db_utils


@admin.route("/authorized-emails")
@admin_required
def manage_authorized_emails():
    """Manage authorized emails for self-registration"""
    emails = db_utils.get_all_authorized_emails()
    return render_template(
        "admin_authorized_emails.html",
        page_name="Manage Authorized Emails",
        emails=emails,
    )


@admin.route("/add-authorized-email", methods=["POST"])
@admin_required
def add_authorized_email():
    """Add new authorized rullenummer (email is optional)"""
    email = request.form.get("email", "").lower().strip() or None
    rullenummer = request.form.get("rullenummer", "").strip()
    notes = request.form.get("notes", "").strip()

    if not rullenummer:
        flash("Rullenummer er påkrevd.", "danger")
        return redirect(url_for("admin.manage_authorized_emails"))

    success, message = db_utils.add_authorized_email(
        email=email, added_by=current_user.id, notes=notes, rullenummer=rullenummer
    )

    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_authorized_emails"))


@admin.route("/delete-authorized-email/<int:email_id>", methods=["POST"])
@admin_required
def delete_authorized_email(email_id):
    """Remove authorized email"""
    success, message = db_utils.delete_authorized_email(email_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.manage_authorized_emails"))


@admin.route("/bulk-add-emails", methods=["POST"])
@admin_required
def bulk_add_authorized_emails():
    """Bulk add emails from textarea (one per line)"""
    emails_text = request.form.get("emails_bulk", "")
    emails = [e.strip().lower() for e in emails_text.split("\n") if e.strip()]

    added_count = 0
    for email in emails:
        success, _ = db_utils.add_authorized_email(
            email=email, added_by=current_user.id, notes="Masseimport"
        )
        if success:
            added_count += 1

    flash(f"La til {added_count} av {len(emails)} e-poster.", "success")
    return redirect(url_for("admin.manage_authorized_emails"))
