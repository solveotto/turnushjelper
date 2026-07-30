"""Tests for app/services/feedback_service.py"""

from unittest.mock import patch

from app.models import DBUser
from app.services.user_helpers import hash_password
from app.services import feedback_service


def _mock_send(return_value=True):
    return patch("app.utils.email_utils.send_mailgun_email", return_value=return_value)


class TestSendFeedback:
    def test_sends_to_support_with_category_in_subject(self, app, sample_user):
        with app.test_request_context(), _mock_send() as mock_send:
            feedback_service.send_feedback(
                sample_user["id"], sample_user["username"], "Feil",
                "Noe er galt", "https://turnushjelper.no/oversikt",
            )
        args, kwargs = mock_send.call_args
        assert args[0] == "support@turnushjelper.no"
        assert "Feil" in args[1]
        assert sample_user["username"] in args[1]

    def test_body_includes_message_and_page_url(self, app, sample_user):
        with app.test_request_context(), _mock_send() as mock_send:
            feedback_service.send_feedback(
                sample_user["id"], sample_user["username"], "Spørsmål",
                "Hvordan fungerer dette?", "https://turnushjelper.no/turnusliste",
            )
        args, _ = mock_send.call_args
        text_body = args[2]
        assert "Hvordan fungerer dette?" in text_body
        assert "https://turnushjelper.no/turnusliste" in text_body

    def test_sets_reply_to_when_user_has_email(self, app, sample_user):
        with app.test_request_context(), _mock_send() as mock_send:
            feedback_service.send_feedback(
                sample_user["id"], sample_user["username"], "Annet",
                "msg", "https://turnushjelper.no/",
            )
        _, kwargs = mock_send.call_args
        assert kwargs["reply_to"] == "testuser@example.com"

    def test_omits_reply_to_when_user_has_no_email(self, app, db_session):
        user = DBUser(username="noemail", password=hash_password("pw"), is_auth=0)
        db_session.add(user)
        db_session.commit()

        with app.test_request_context(), _mock_send() as mock_send:
            feedback_service.send_feedback(
                user.id, "noemail", "Annet", "msg", "https://turnushjelper.no/",
            )
        _, kwargs = mock_send.call_args
        assert kwargs.get("reply_to") is None

    def test_returns_false_on_email_failure(self, app, sample_user):
        with app.test_request_context(), _mock_send(return_value=False):
            success, _ = feedback_service.send_feedback(
                sample_user["id"], sample_user["username"], "Annet",
                "msg", "https://turnushjelper.no/",
            )
        assert success is False

    def test_returns_true_on_email_success(self, app, sample_user):
        with app.test_request_context(), _mock_send(return_value=True):
            success, _ = feedback_service.send_feedback(
                sample_user["id"], sample_user["username"], "Annet",
                "msg", "https://turnushjelper.no/",
            )
        assert success is True
