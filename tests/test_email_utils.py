"""Tests for app/utils/email_utils.py"""

from unittest.mock import patch, MagicMock

from app.utils.email_utils import send_mailgun_email


def _mock_response(status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = ""
    return resp


class TestSendMailgunEmailReplyTo:
    def test_includes_reply_to_header_when_given(self):
        with patch("app.utils.email_utils.requests.post") as mock_post:
            mock_post.return_value = _mock_response()
            send_mailgun_email(
                "to@example.com", "Subject", "text", "<p>html</p>",
                reply_to="reply@example.com",
            )
            _, kwargs = mock_post.call_args
            assert kwargs["data"]["h:Reply-To"] == "reply@example.com"

    def test_omits_reply_to_header_when_not_given(self):
        with patch("app.utils.email_utils.requests.post") as mock_post:
            mock_post.return_value = _mock_response()
            send_mailgun_email("to@example.com", "Subject", "text", "<p>html</p>")
            _, kwargs = mock_post.call_args
            assert "h:Reply-To" not in kwargs["data"]


class TestSendMailgunEmailHeaders:
    def test_extra_headers_are_passed_with_the_mailgun_prefix(self):
        with patch("app.utils.email_utils.requests.post") as mock_post:
            mock_post.return_value = _mock_response()
            send_mailgun_email(
                "to@example.com", "Subject", "text", "<p>html</p>",
                headers={"List-Unsubscribe": "<https://x.test/a>"},
            )
            _, kwargs = mock_post.call_args
            assert kwargs["data"]["h:List-Unsubscribe"] == "<https://x.test/a>"

    def test_no_extra_headers_by_default(self):
        with patch("app.utils.email_utils.requests.post") as mock_post:
            mock_post.return_value = _mock_response()
            send_mailgun_email("to@example.com", "Subject", "text", "<p>html</p>")
            _, kwargs = mock_post.call_args
            assert not [key for key in kwargs["data"] if key.startswith("h:")]
