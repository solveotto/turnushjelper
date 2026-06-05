import logging
import os
import pickle
import random
from datetime import datetime, timedelta, timezone

from flask.sessions import SessionInterface, SessionMixin
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import CallbackDict

from app.database import SessionLocal

logger = logging.getLogger(__name__)


class FlaskSession(CallbackDict, SessionMixin):
    """Server-side session object backed by a DB row."""

    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True

        super().__init__(initial or {}, on_update)
        self.sid = sid
        self.new = new
        self.modified = False


class SqlAlchemySessionInterface(SessionInterface):
    """Stores sessions in the flask_sessions DB table via existing SQLAlchemy engine."""

    def __init__(self, cleanup_probability: float = 0.01):
        self.cleanup_probability = cleanup_probability

    def _generate_sid(self) -> str:
        return os.urandom(32).hex()

    def open_session(self, app, request) -> FlaskSession:
        cookie_value = request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"))
        if not cookie_value:
            return FlaskSession(sid=self._generate_sid(), new=True)

        try:
            sid = URLSafeSerializer(app.secret_key).loads(cookie_value)
        except BadSignature:
            return FlaskSession(sid=self._generate_sid(), new=True)

        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is None or row.expiry < datetime.now(timezone.utc).replace(tzinfo=None):
                if row is not None:
                    db.delete(row)
                    db.commit()
                return FlaskSession(sid=self._generate_sid(), new=True)
            return FlaskSession(pickle.loads(row.data), sid=sid)
        except Exception:
            logger.exception("Session open failed")
            return FlaskSession(sid=self._generate_sid(), new=True)
        finally:
            db.close()

    def save_session(self, app, session, response) -> None:
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")

        if not session:
            if not session.new:
                # Existing session was cleared (e.g. logout) — delete DB row and clear cookie.
                from app.models import FlaskSessionModel

                db = SessionLocal()
                try:
                    db.query(FlaskSessionModel).filter_by(session_id=session.sid).delete()
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Session delete failed on logout")
                finally:
                    db.close()
                response.delete_cookie(cookie_name, domain=domain, path=path)
            return

        if session.permanent:
            expiry = datetime.now(timezone.utc).replace(tzinfo=None) + app.permanent_session_lifetime
        else:
            # Non-permanent: cookie expires at browser close; server-side row lives for full lifetime.
            expiry = datetime.now(timezone.utc).replace(tzinfo=None) + app.permanent_session_lifetime

        sid = session.sid
        data = pickle.dumps(dict(session))

        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
            else:
                db.add(FlaskSessionModel(session_id=sid, data=data, expiry=expiry))
            db.commit()
        except IntegrityError:
            # Race: two threads created the same sid concurrently.
            db.rollback()
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
                try:
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            db.rollback()
            logger.exception("Session save failed")
        finally:
            db.close()

        if random.random() < self.cleanup_probability:
            self._delete_expired()

        signed_sid = URLSafeSerializer(app.secret_key).dumps(sid)
        if self.should_set_cookie(app, session):
            response.set_cookie(
                cookie_name,
                signed_sid,
                expires=expiry if session.permanent else None,
                httponly=self.get_cookie_httponly(app),
                domain=domain,
                path=path,
                secure=self.get_cookie_secure(app),
                samesite=self.get_cookie_samesite(app),
            )

    def regenerate(self, session: FlaskSession) -> None:
        """Assign a new session ID, deleting the old DB row. Call on login to prevent fixation."""
        old_sid = session.sid
        if old_sid:
            from app.models import FlaskSessionModel
            db = SessionLocal()
            try:
                db.query(FlaskSessionModel).filter_by(session_id=old_sid).delete()
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Session regeneration delete failed")
            finally:
                db.close()
        session.sid = self._generate_sid()
        session.modified = True

    def _delete_expired(self) -> None:
        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            db.query(FlaskSessionModel).filter(
                FlaskSessionModel.expiry < datetime.now(timezone.utc).replace(tzinfo=None)
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Session cleanup failed")
        finally:
            db.close()
