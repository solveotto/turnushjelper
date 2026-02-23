import logging
from datetime import datetime, timedelta

from config import AppConfig
from app.database import get_db_session
from app.models import DBUser, AuthorizedEmails, EmailVerificationToken

logger = logging.getLogger(__name__)


def is_email_authorized(email, rullenummer=None):
    """Check if rullenummer is in the authorized list (email is ignored for authorization)"""
    if not rullenummer:
        return False
    db_session = get_db_session()
    try:
        result = db_session.query(AuthorizedEmails).filter_by(rullenummer=rullenummer).first()
        return result is not None
    finally:
        db_session.close()


def add_authorized_email(email=None, added_by=None, notes='', rullenummer=None):
    """Add a rullenummer (and optional email) to the authorized list"""
    if not rullenummer:
        return False, "Rullenummer er påkrevd"

    db_session = get_db_session()
    try:
        existing = db_session.query(AuthorizedEmails).filter_by(rullenummer=rullenummer).first()
        if existing:
            return False, "Rullenummeret finnes allerede i autorisert liste"

        new_entry = AuthorizedEmails(
            email=email.lower() if email else None,
            rullenummer=rullenummer,
            added_by=added_by,
            notes=notes
        )
        db_session.add(new_entry)
        db_session.commit()
        return True, "Rullenummer lagt til i autorisert liste"
    except Exception as e:
        db_session.rollback()
        return False, f"Error adding entry: {e}"
    finally:
        db_session.close()


def get_all_authorized_emails():
    """Get all authorized emails with additional info"""
    db_session = get_db_session()
    try:
        emails = db_session.query(AuthorizedEmails).order_by(AuthorizedEmails.added_at.desc()).all()
        result = []
        for email in emails:
            user = db_session.query(DBUser).filter_by(email=email.email).first()
            admin = db_session.query(DBUser).filter_by(id=email.added_by).first()

            result.append({
                'id': email.id,
                'email': email.email,
                'rullenummer': email.rullenummer,
                'added_by': email.added_by,
                'added_by_username': admin.username if admin else None,
                'added_at': email.added_at,
                'notes': email.notes,
                'is_registered': user is not None
            })
        return result
    finally:
        db_session.close()


def delete_authorized_email(email_id):
    """Remove email from authorized list"""
    db_session = get_db_session()
    try:
        email = db_session.query(AuthorizedEmails).filter_by(id=email_id).first()
        if not email:
            return False, "E-post ikke funnet"

        db_session.delete(email)
        db_session.commit()
        return True, "E-post fjernet fra autorisert liste"
    except Exception as e:
        db_session.rollback()
        return False, f"Error removing email: {e}"
    finally:
        db_session.close()


def create_verification_token(user_id, token):
    """Create email verification token"""
    db_session = get_db_session()
    try:
        expiry_hours = AppConfig.TOKEN_EXPIRY_HOURS
        expires_at = datetime.now() + timedelta(hours=expiry_hours)

        db_session.query(EmailVerificationToken).filter_by(
            user_id=user_id,
            used=0
        ).update({'used': 1})

        new_token = EmailVerificationToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        db_session.add(new_token)
        db_session.commit()
        return True, "Verifiseringstoken opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating token: %s", e)
        return False, f"Error creating token: {e}"
    finally:
        db_session.close()


def verify_token(token):
    """Verify email verification token and mark user as verified"""
    db_session = get_db_session()
    try:
        token_record = db_session.query(EmailVerificationToken).filter_by(
            token=token,
            used=0
        ).first()

        if not token_record:
            return {'success': False, 'message': 'Ugyldig eller allerede brukt verifiseringslenke'}

        if token_record.expires_at < datetime.now():
            return {'success': False, 'message': 'Verifiseringslenken har utløpt. Vennligst be om en ny.'}

        token_record.used = 1

        user = db_session.query(DBUser).filter_by(id=token_record.user_id).first()
        if user:
            user.email_verified = 1
            db_session.commit()
            return {'success': True, 'message': 'E-post verifisert', 'email': user.email}
        else:
            return {'success': False, 'message': 'Bruker ikke funnet'}

    except Exception as e:
        db_session.rollback()
        logger.error("Error verifying token: %s", e)
        return {'success': False, 'message': 'En feil oppstod under verifisering'}
    finally:
        db_session.close()


def can_send_verification_email(user_id):
    """Check rate limiting for verification emails"""
    db_session = get_db_session()
    try:
        max_per_day = AppConfig.MAX_VERIFICATION_EMAILS_PER_DAY

        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False

        if user.verification_sent_at:
            time_since_last = datetime.now() - user.verification_sent_at
            if time_since_last < timedelta(hours=1):
                return False

        count = db_session.query(EmailVerificationToken).filter(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.created_at >= datetime.now() - timedelta(days=1)
        ).count()

        return count < max_per_day
    finally:
        db_session.close()


def update_verification_sent_time(email):
    """Update timestamp when verification email was sent"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if user:
            user.verification_sent_at = datetime.now()
            db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error("Error updating verification sent time: %s", e)
    finally:
        db_session.close()


def create_password_reset_token(user_id, token):
    """Create password reset token with 1 hour expiry"""
    db_session = get_db_session()
    try:
        expires_at = datetime.now() + timedelta(hours=1)

        db_session.query(EmailVerificationToken).filter_by(
            user_id=user_id,
            token_type='password_reset',
            used=0
        ).update({'used': 1})

        new_token = EmailVerificationToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            token_type='password_reset'
        )
        db_session.add(new_token)
        db_session.commit()
        return True, "Tilbakestillingstoken opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating password reset token: %s", e)
        return False, f"Error creating password reset token: {e}"
    finally:
        db_session.close()


def verify_password_reset_token(token):
    """Verify password reset token and return user info if valid"""
    db_session = get_db_session()
    try:
        token_record = db_session.query(EmailVerificationToken).filter_by(
            token=token,
            token_type='password_reset',
            used=0
        ).first()

        if not token_record:
            return {'success': False, 'message': 'Ugyldig eller allerede brukt tilbakestillingslenke'}

        if token_record.expires_at < datetime.now():
            return {'success': False, 'message': 'Tilbakestillingslenken har utløpt. Vennligst be om en ny.'}

        user = db_session.query(DBUser).filter_by(id=token_record.user_id).first()
        if user:
            return {
                'success': True,
                'user_id': user.id,
                'email': user.email,
                'username': user.username
            }
        else:
            return {'success': False, 'message': 'Bruker ikke funnet'}

    except Exception as e:
        logger.error("Error verifying password reset token: %s", e)
        return {'success': False, 'message': 'En feil oppstod under verifisering'}
    finally:
        db_session.close()


def reset_user_password(user_id, new_password):
    """Update user password and mark reset token as used"""
    from app.services.user_service import hash_password
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        user.password = hash_password(new_password)

        db_session.query(EmailVerificationToken).filter_by(
            user_id=user_id,
            token_type='password_reset',
            used=0
        ).update({'used': 1})

        db_session.commit()
        return True, "Passord oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating password: {e}"
    finally:
        db_session.close()


def can_send_password_reset_email(email):
    """Check rate limiting for password reset emails (1 per hour per email)"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if not user:
            return True

        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_token = db_session.query(EmailVerificationToken).filter(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token_type == 'password_reset',
            EmailVerificationToken.created_at >= one_hour_ago
        ).first()

        return recent_token is None
    finally:
        db_session.close()
