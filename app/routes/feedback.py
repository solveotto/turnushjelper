from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.extensions import limiter
from app.forms import FeedbackForm
from app.services import feedback_service

feedback = Blueprint("feedback", __name__, url_prefix="/feedback")


@feedback.route("/send", methods=["POST"])
@login_required
@limiter.limit("5 per hour", key_func=lambda: str(current_user.id))
def send():
    """Email the submitted feedback/support message to support@turnushjelper.no"""
    form = FeedbackForm()
    if not form.validate_on_submit():
        return jsonify(success=False, error="Ugyldig skjema"), 400

    success, message = feedback_service.send_feedback(
        current_user.id,
        current_user.username,
        form.category.data,
        form.message.data,
        form.page_url.data,
    )

    if success:
        return jsonify(success=True)
    return jsonify(success=False, error=message), 502
