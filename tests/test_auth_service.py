"""Tests for app.services.auth_service."""

import uuid
from datetime import datetime, timedelta

from app.models import EmailVerificationToken
from app.services import auth_service, user_service


class TestAuthorizedEmails:
    def test_add_and_check(self, patch_db, sample_user):
        success, _ = auth_service.add_authorized_email(
            "allowed@test.com", added_by=sample_user["id"]
        )
        assert success is True
        assert auth_service.is_email_authorized("allowed@test.com") is True
        assert auth_service.is_email_authorized("other@test.com") is False


class TestVerificationToken:
    def test_create_and_verify(self, patch_db, db_session, sample_user):
        token = uuid.uuid4().hex
        success, _ = auth_service.create_verification_token(sample_user["id"], token)
        assert success is True

        result = auth_service.verify_token(token)
        assert result["success"] is True

        # User should now be email_verified
        data = user_service.get_user_data(sample_user["username"])
        assert data["email_verified"] == 1

    def test_verify_expired_token(self, patch_db, db_session, sample_user):
        token = uuid.uuid4().hex
        auth_service.create_verification_token(sample_user["id"], token)

        # Manually expire the token
        record = db_session.query(EmailVerificationToken).filter_by(token=token).first()
        record.expires_at = datetime.now() - timedelta(hours=1)
        db_session.commit()

        result = auth_service.verify_token(token)
        assert result["success"] is False
        assert "utløpt" in result["message"]


class TestPasswordResetToken:
    def test_full_reset_flow(self, patch_db, sample_user):
        token = uuid.uuid4().hex
        success, _ = auth_service.create_password_reset_token(sample_user["id"], token)
        assert success is True

        result = auth_service.verify_password_reset_token(token)
        assert result["success"] is True
        assert result["user_id"] == sample_user["id"]
