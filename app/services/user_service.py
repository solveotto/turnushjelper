import logging

import bcrypt
from sqlalchemy import func

from app.database import get_db_session
from app.models import DBUser, Favorites

logger = logging.getLogger(__name__)


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_pw.decode("utf-8")


def create_new_user(username, password, is_auth):
    db_session = get_db_session()
    try:
        new_user = DBUser(
            username=username, password=hash_password(password), is_auth=is_auth
        )
        db_session.add(new_user)
        db_session.commit()
        logger.info("User created")
        return True, "Bruker opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating user: %s", e)
        return False, f"Error creating user: {e}"
    finally:
        db_session.close()


def get_user_data(username_or_email):
    """Get user data by username or email"""
    db_session = get_db_session()
    try:
        result = db_session.query(DBUser).filter_by(username=username_or_email).first()

        if not result:
            result = (
                db_session.query(DBUser)
                .filter_by(email=username_or_email.lower())
                .first()
            )

        if result:
            data = {
                "id": result.id,
                "username": result.username,
                "password": result.password,
                "is_auth": result.is_auth,
                "email": result.email,
                "email_verified": result.email_verified,
            }
            return data
        else:
            logger.warning("User not found: %s", username_or_email)
            return None
    finally:
        db_session.close()


def get_user_password(username):
    db_session = get_db_session()
    try:
        result = db_session.query(DBUser.password).filter_by(username=username).first()
        return result.password if result else None
    finally:
        db_session.close()


def get_user_by_email(email):
    """Get user by email address"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "is_auth": user.is_auth,
                "created_at": user.created_at,
                "password": user.password,
            }
        return None
    finally:
        db_session.close()


def get_user_by_username(username):
    """Get user by username"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(username=username).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "is_auth": user.is_auth,
            }
        return None
    finally:
        db_session.close()


def create_user_with_email(email, username, password, verified=False, rullenummer=None):
    """Create user account with email (for self-registration)"""
    db_session = get_db_session()
    try:
        existing_email = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if existing_email:
            return False, "E-postadressen er allerede registrert", None

        existing_username = (
            db_session.query(DBUser).filter_by(username=username).first()
        )
        if existing_username:
            return False, "Brukernavnet er allerede tatt", None

        new_user = DBUser(
            username=username,
            email=email.lower(),
            password=hash_password(password),
            rullenummer=rullenummer,
            is_auth=0,
            email_verified=1 if verified else 0,
            created_at=func.now(),
        )
        db_session.add(new_user)
        db_session.commit()
        db_session.refresh(new_user)
        return True, "Bruker opprettet", new_user.id
    except Exception as e:
        db_session.rollback()
        return False, f"Error creating user: {e}", None
    finally:
        db_session.close()


def get_all_users():
    """Get all users from the database"""
    db_session = get_db_session()
    try:
        users = db_session.query(DBUser).all()
        return [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "rullenummer": user.rullenummer,
                "is_auth": user.is_auth,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
            }
            for user in users
        ]
    finally:
        db_session.close()


def get_user_by_id(user_id):
    """Get a specific user by ID"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "rullenummer": user.rullenummer,
                "is_auth": user.is_auth,
            }
        return None
    finally:
        db_session.close()


def create_user(username, password, is_auth=0):
    """Create a new user (admin-created users are auto-verified)"""
    db_session = get_db_session()
    try:
        existing_user = db_session.query(DBUser).filter_by(username=username).first()
        if existing_user:
            return False, "Brukernavnet finnes allerede"

        new_user = DBUser(
            username=username,
            email=username,
            password=hash_password(password),
            is_auth=is_auth,
            email_verified=1,
            created_at=func.now(),
        )
        db_session.add(new_user)
        db_session.commit()
        return True, "Bruker opprettet"
    except Exception as e:
        db_session.rollback()
        return False, f"Error creating user: {e}"
    finally:
        db_session.close()


def update_user(
    user_id, username, email=None, rullenummer=None, password=None, is_auth=None
):
    """Update an existing user"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        if username != user.username:
            existing_user = (
                db_session.query(DBUser).filter_by(username=username).first()
            )
            if existing_user:
                return False, "Brukernavnet finnes allerede"

        if email and email != user.email:
            existing_email = (
                db_session.query(DBUser).filter_by(email=email.lower()).first()
            )
            if existing_email:
                return False, "E-postadressen finnes allerede"

        user.username = username
        if email is not None:
            user.email = email.lower()
        if rullenummer is not None:
            user.rullenummer = rullenummer
        if password:
            user.password = hash_password(password)
        if is_auth is not None:
            user.is_auth = is_auth

        db_session.commit()
        return True, "Bruker oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating user: {e}"
    finally:
        db_session.close()


def delete_user(user_id):
    """Delete a user and all associated data"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        db_session.query(Favorites).filter_by(user_id=user_id).delete()
        db_session.delete(user)
        db_session.commit()
        return True, "Bruker slettet"
    except Exception as e:
        db_session.rollback()
        return False, f"Error deleting user: {e}"
    finally:
        db_session.close()


def toggle_user_auth(user_id):
    """Toggle user authentication status"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        user.is_auth = 1 if user.is_auth == 0 else 0
        db_session.commit()
        return (
            True,
            f"Administratorrettigheter {'aktivert' if user.is_auth == 1 else 'deaktivert'}",
        )
    except Exception as e:
        db_session.rollback()
        return False, f"Error toggling user auth: {e}"
    finally:
        db_session.close()


def update_user_password(user_id, current_password, new_password):
    """Update user password with current password verification"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        if not bcrypt.checkpw(
            current_password.encode("utf-8"), user.password.encode("utf-8")
        ):
            return False, "Nåværende passord er feil"

        user.password = hash_password(new_password)
        db_session.commit()
        return True, "Passord oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating password: {e}"
    finally:
        db_session.close()


def init_default_admin():
    """Creates a default admin user if database is empty"""
    from config import AppConfig

    db_session = get_db_session()
    try:
        if db_session.query(DBUser).count() > 0:
            return

        if not AppConfig.DEFAULT_ADMIN_PASSWORD:
            logger.warning("No DEFAULT_ADMIN_PASSWORD set, skipping admin creation")
            return

        admin = DBUser(
            username=AppConfig.DEFAULT_ADMIN_USERNAME,
            email=AppConfig.DEFAULT_ADMIN_USERNAME,
            password=hash_password(AppConfig.DEFAULT_ADMIN_PASSWORD),
            is_auth=1,
            email_verified=1,
        )
        db_session.add(admin)
        db_session.commit()
        logger.info("Default admin created: %s", AppConfig.DEFAULT_ADMIN_USERNAME)
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating default admin: %s", e)
    finally:
        db_session.close()
