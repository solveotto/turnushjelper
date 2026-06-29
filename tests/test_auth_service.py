"""Tests for app.services.auth_service."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models import EmailVerificationToken
from app.services import auth_service, user_service


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
        record.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        db_session.commit()

        result = auth_service.verify_token(token)
        assert result["success"] is False
        assert "utløpt" in result["message"]


class TestPurgeExpiredTokens:
    def test_purges_only_expired_tokens(self, patch_db, db_session, sample_user):
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Expired (used) and expired (unused) — both should go
        db_session.add(EmailVerificationToken(
            user_id=sample_user["id"], token="expired-used",
            expires_at=now - timedelta(hours=2), used=1,
        ))
        db_session.add(EmailVerificationToken(
            user_id=sample_user["id"], token="expired-unused",
            expires_at=now - timedelta(days=1), used=0,
        ))
        # Still valid — should be kept
        db_session.add(EmailVerificationToken(
            user_id=sample_user["id"], token="valid",
            expires_at=now + timedelta(hours=1), used=0,
        ))
        db_session.commit()

        deleted = auth_service.purge_expired_tokens()

        assert deleted == 2
        remaining = db_session.query(EmailVerificationToken).all()
        assert [t.token for t in remaining] == ["valid"]


class TestTokenExpiry:
    def test_expired_token_is_rejected(self, patch_db, db_session, sample_user):
        from app.models import EmailVerificationToken

        expired_token = EmailVerificationToken(
            user_id=sample_user["id"],
            token="expired-tok-123",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
            used=0,
        )
        db_session.add(expired_token)
        db_session.commit()

        result = auth_service.verify_token("expired-tok-123")
        assert result["success"] is False
        assert "utløpt" in result["message"]

    def test_valid_token_is_accepted(self, patch_db, db_session, sample_user):
        from app.models import EmailVerificationToken

        valid_token = EmailVerificationToken(
            user_id=sample_user["id"],
            token="valid-tok-456",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48),
            used=0,
        )
        db_session.add(valid_token)
        db_session.commit()

        result = auth_service.verify_token("valid-tok-456")
        assert result["success"] is True


class TestPasswordResetToken:
    def test_full_reset_flow(self, patch_db, sample_user):
        token = uuid.uuid4().hex
        success, _ = auth_service.create_password_reset_token(sample_user["id"], token)
        assert success is True

        result = auth_service.verify_password_reset_token(token)
        assert result["success"] is True
        assert result["user_id"] == sample_user["id"]
