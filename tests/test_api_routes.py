"""Tests for API routes (toggle_favorite)."""

import json

from tests.conftest import login_user
from app.models import TurnusSet


class TestToggleFavoriteAuth:
    def test_requires_login(self, client):
        """Unauthenticated POST should redirect to login."""
        resp = client.post(
            "/api/toggle_favorite",
            data=json.dumps({"shift_title": "D1", "favorite": True}),
            content_type="application/json",
        )
        # Should redirect to login (302)
        assert resp.status_code == 302


class TestToggleFavorite:
    def test_add_favorite(self, client, db_session, sample_user):
        # Create an active turnus set
        ts = TurnusSet(name="API Test Set", year_identifier="A25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        login_user(client, sample_user["username"], sample_user["password"])

        # Set turnus set in session
        with client.session_transaction() as sess:
            sess["user_selected_turnus_set"] = ts.id

        resp = client.post(
            "/api/toggle_favorite",
            data=json.dumps({"shift_title": "D1", "favorite": True}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "success"

    def test_remove_favorite(self, client, db_session, sample_user):
        ts = TurnusSet(name="API Test Set", year_identifier="A25", is_active=1)
        db_session.add(ts)
        db_session.commit()

        login_user(client, sample_user["username"], sample_user["password"])

        with client.session_transaction() as sess:
            sess["user_selected_turnus_set"] = ts.id

        # Add then remove
        client.post(
            "/api/toggle_favorite",
            data=json.dumps({"shift_title": "D1", "favorite": True}),
            content_type="application/json",
        )
        resp = client.post(
            "/api/toggle_favorite",
            data=json.dumps({"shift_title": "D1", "favorite": False}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "success"
