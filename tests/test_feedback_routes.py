"""Tests for app/routes/feedback.py"""

import re

from tests.conftest import login_user


class TestFeedbackModalRendersInBase:
    def test_kontakt_link_and_modal_present(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get("/minside/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'id="feedbackModal"' in html

        link_match = re.search(
            r'data-bs-target="#feedbackModal"[^>]*>(.*?)</a>', html, re.DOTALL
        )
        assert link_match, "menu item linking to the feedback modal is missing"
        assert link_match.group(1).split()[-1] == "Kontakt"


def _valid_payload(**overrides):
    payload = {
        "category": "Feil",
        "message": "Noe er galt med turnuslisten",
        "page_url": "https://turnushjelper.no/turnusliste",
    }
    payload.update(overrides)
    return payload


class TestFeedbackAuth:
    def test_requires_login(self, client, patch_db):
        resp = client.post("/feedback/send", data=_valid_payload())
        assert resp.status_code in (302, 401)


class TestFeedbackSubmit:
    def test_valid_submission_returns_success(self, client, sample_user, monkeypatch):
        login_user(client, sample_user["username"], sample_user["password"])
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: (True, "sent"),
        )
        resp = client.post("/feedback/send", data=_valid_payload())
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_service_called_with_form_data(self, client, sample_user, monkeypatch):
        login_user(client, sample_user["username"], sample_user["password"])
        calls = []
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: calls.append(a) or (True, "sent"),
        )
        client.post("/feedback/send", data=_valid_payload(category="Spørsmål", message="Hei?"))
        assert calls[0][0] == sample_user["id"]
        assert calls[0][2] == "Spørsmål"
        assert calls[0][3] == "Hei?"

    def test_tilbakemelding_category_accepted(self, client, sample_user, monkeypatch):
        login_user(client, sample_user["username"], sample_user["password"])
        calls = []
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: calls.append(a) or (True, "sent"),
        )
        resp = client.post(
            "/feedback/send", data=_valid_payload(category="Tilbakemelding")
        )
        assert resp.status_code == 200
        assert calls[0][2] == "Tilbakemelding"

    def test_empty_message_rejected(self, client, sample_user, monkeypatch):
        login_user(client, sample_user["username"], sample_user["password"])
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: (True, "sent"),
        )
        resp = client.post("/feedback/send", data=_valid_payload(message=""))
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_email_failure_returns_error(self, client, sample_user, monkeypatch):
        login_user(client, sample_user["username"], sample_user["password"])
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: (False, "Kunne ikke sende tilbakemelding"),
        )
        resp = client.post("/feedback/send", data=_valid_payload())
        assert resp.status_code == 502
        assert resp.get_json()["success"] is False


class TestFeedbackCsrf:
    def test_apifetch_style_header_satisfies_csrf_with_enforcement_on(
        self, app, sample_user, monkeypatch
    ):
        """The modal form has no csrf_token field of its own - it relies on
        apiFetch always attaching X-CSRFToken from the page's <meta
        name="csrf-token"> tag. That satisfies the app-wide CSRFProtect
        check, which then marks the request CSRF-valid (g.csrf_valid) before
        FlaskForm's own per-field check runs, so the header alone is
        sufficient - confirmed here with real CSRF enforcement on, not the
        suite-wide disabled config."""
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: (True, "sent"),
        )
        test_client = app.test_client()
        # Log in before turning CSRF on - login_user() posts without a
        # token, so it must run while CSRF is still disabled.
        login_user(test_client, sample_user["username"], sample_user["password"])
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            # Grab the token from any authenticated base.html page's meta
            # tag, same as the real page's JS does.
            page_html = test_client.get("/favorites").data.decode()
            match = re.search(r'name="csrf-token" content="([^"]+)"', page_html)
            assert match, "base.html must render the csrf-token meta tag"
            token = match.group(1)

            resp = test_client.post(
                "/feedback/send",
                data=_valid_payload(),
                headers={"X-CSRFToken": token},
            )
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True

            # Sanity check: without the header, the request must be rejected.
            resp_no_header = test_client.post("/feedback/send", data=_valid_payload())
            assert resp_no_header.status_code != 200
        finally:
            app.config["WTF_CSRF_ENABLED"] = False


class TestFeedbackRateLimit:
    def test_rate_limited_after_5_requests_per_user(self, app, sample_user, admin_user, monkeypatch):
        monkeypatch.setattr(
            "app.routes.feedback.feedback_service.send_feedback",
            lambda *a, **k: (True, "sent"),
        )
        from app.extensions import limiter

        limiter.reset()
        limiter.enabled = True
        try:
            client_a = app.test_client()
            login_user(client_a, sample_user["username"], sample_user["password"])
            for _ in range(5):
                resp = client_a.post("/feedback/send", data=_valid_payload())
                assert resp.status_code == 200
            resp = client_a.post("/feedback/send", data=_valid_payload())
            assert resp.status_code == 429

            # A different user is not blocked by the first user's limit.
            client_b = app.test_client()
            login_user(client_b, admin_user["username"], admin_user["password"])
            resp = client_b.post("/feedback/send", data=_valid_payload())
            assert resp.status_code == 200
        finally:
            limiter.enabled = False
            limiter.reset()
