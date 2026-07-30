import json
import logging
import os
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
    """Stores sessions (JSON-serialized) in the flask_sessions DB table via the existing SQLAlchemy engine."""

    def __init__(self, cleanup_probability: float = 0.01):
        self.cleanup_probability = cleanup_probability

    def _generate_sid(self) -> str:
        return os.urandom(32).hex()

    def open_session(self, app, request) -> FlaskSession:
        # Every branch below that returns a fresh session is a logout from the
        # user's point of view, so each one is tagged distinctly: in production
        # they are otherwise indistinguishable. A nonzero "bad_signature" count
        # means SECRET_KEY is not stable across workers/hosts.
        cookie_value = request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"))
        if not cookie_value:
            # Fires on every genuine first visit — DEBUG so it cannot drown the
            # branches that actually indicate a problem.
            logger.debug("session_fresh: no cookie presented")
            return FlaskSession(sid=self._generate_sid(), new=True)

        try:
            sid = URLSafeSerializer(app.secret_key).loads(cookie_value)
        except BadSignature:
            logger.info("session_fresh: bad_signature (cookie not signed by this SECRET_KEY)")
            return FlaskSession(sid=self._generate_sid(), new=True)

        from app.models import FlaskSessionModel

        db = SessionLocal()
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is None:
                logger.info("session_fresh: row_missing (valid cookie, no DB row)")
                return FlaskSession(sid=self._generate_sid(), new=True)
            if row.expiry < datetime.now(timezone.utc).replace(tzinfo=None):
                logger.info("session_fresh: row_expired (expiry %s)", row.expiry)
                db.delete(row)
                db.commit()
                return FlaskSession(sid=self._generate_sid(), new=True)
            return FlaskSession(json.loads(row.data), sid=sid)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            # Legacy pickle-serialized rows written before the JSON cut-over:
            # they fail json.loads and are treated as a fresh session (a one-time
            # logout on deploy — acceptable, tokens re-issued).
            logger.info("session_fresh: decode_failed (stored data is not JSON)")
            return FlaskSession(sid=self._generate_sid(), new=True)
        # NOTE: SQLAlchemyError is deliberately NOT caught. Returning a fresh
        # session here would be silent, permanent data loss rather than a blip:
        # csrf_token() runs on every page render, so the fresh session is never
        # empty, and save_session would then INSERT a row under the new sid and
        # overwrite the still-valid cookie — orphaning the user's real session
        # row. Letting a transient DB error surface as a 500 leaves the cookie
        # untouched, so the next request finds the session intact.
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

        expiry = datetime.now(timezone.utc).replace(tzinfo=None) + app.permanent_session_lifetime

        sid = session.sid
        data = json.dumps(dict(session)).encode("utf-8")

        from app.models import FlaskSessionModel

        db = SessionLocal()
        session_saved = False
        is_insert = False
        try:
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
            else:
                is_insert = True
                db.add(FlaskSessionModel(session_id=sid, data=data, expiry=expiry))
            db.commit()
            session_saved = True
        except IntegrityError:
            # Race: two threads created the same sid concurrently.
            db.rollback()
            row = db.query(FlaskSessionModel).filter_by(session_id=sid).first()
            if row is not None:
                row.data = data
                row.expiry = expiry
                try:
                    db.commit()
                    session_saved = True
                except Exception:
                    db.rollback()
        except Exception:
            db.rollback()
            if is_insert:
                # No prior row survives an INSERT failure. At login, regenerate()
                # has already deleted the old row, so the session is genuinely
                # lost and the user lands back on the login page. This is the one
                # save-path failure that logs someone out.
                logger.error("Session save failed on INSERT — session lost", exc_info=True)
            else:
                # A failed UPDATE rolls back and leaves the existing row intact,
                # so the next request still reads a valid session.
                logger.warning("Session save failed on UPDATE — prior row retained", exc_info=True)
        finally:
            db.close()

        if not session_saved:
            return

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
