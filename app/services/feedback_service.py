import logging

from flask import render_template

from app.database import get_db_session
from app.models import DBUser
from app.utils import email_utils

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "support@turnushjelper.no"


def _get_user_email(user_id):
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter(DBUser.id == user_id).first()
        return user.email if user else None
    finally:
        db_session.close()


def send_feedback(user_id, username, category, message, page_url):
    """Email a user's feedback/support message to support@turnushjelper.no"""
    email = _get_user_email(user_id)

    subject = f"[{category}] Tilbakemelding fra {username}"

    text_body = f"""
Kategori: {category}
Bruker: {username}
E-post: {email or 'ikke oppgitt'}
Side: {page_url}

Melding:
{message}
    """

    html_body = render_template(
        "emails/feedback_email.html",
        category=category,
        username=username,
        email=email,
        page_url=page_url,
        message=message,
    )

    success = email_utils.send_mailgun_email(
        SUPPORT_EMAIL, subject, text_body, html_body, reply_to=email
    )

    if success:
        return True, "Tilbakemeldingen ble sendt"
    return False, "Kunne ikke sende tilbakemelding"
