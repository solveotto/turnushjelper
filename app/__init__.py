import logging

from flask import Flask, session
from flask_login import current_user
from flask_session import Session

from app.database import get_db_session
from app.extensions import cache, limiter, login_manager, mail
from app.models import DBUser, User
from app.services.user_service import init_default_admin
from config import AppConfig

logger = logging.getLogger(__name__)



def create_app():
    app = Flask(__name__)
    app.config.from_object(AppConfig)

    # Email configuration (optional - using Mailgun API by default)
    app.config["MAIL_SERVER"] = AppConfig.SMTP_SERVER
    app.config["MAIL_PORT"] = AppConfig.SMTP_PORT
    app.config["MAIL_USE_TLS"] = AppConfig.SMTP_USE_TLS
    app.config["MAIL_USE_SSL"] = AppConfig.SMTP_USE_SSL
    app.config["MAIL_USERNAME"] = AppConfig.SMTP_USERNAME
    app.config["MAIL_PASSWORD"] = AppConfig.SMTP_PASSWORD
    app.config["MAIL_DEFAULT_SENDER"] = (AppConfig.SENDER_NAME, AppConfig.SENDER_EMAIL)

    # Initialize Flask extensions
    mail.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Creates default admin if no users in database
    init_default_admin()

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_id = int(user_id)
            return User.get_by_id(user_id)
        except (ValueError, TypeError):
            pass
        return None

    # Configure server-side session storage
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = AppConfig.sessions_dir
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_KEY_PREFIX"] = "session:"

    Session(app)

    @app.context_processor
    def inject_tour_state():
        if current_user.is_authenticated:
            from app.models import Innplassering, TurnusSet
            db_session = get_db_session()
            try:
                db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
                has_min_turnus = False
                if db_user and db_user.rullenummer:
                    active_ts = db_session.query(TurnusSet).filter_by(is_active=1).first()
                    if active_ts:
                        has_min_turnus = db_session.query(Innplassering).filter_by(
                            turnus_set_id=active_ts.id,
                            rullenummer=str(db_user.rullenummer),
                        ).first() is not None
                return {
                    "has_seen_tour": session.get('has_seen_tour', 0),
                    "has_seen_favorites_tour": session.get('has_seen_favorites_tour', 0),
                    "has_seen_mintur_tour": session.get('has_seen_mintur_tour', 0),
                    "has_seen_compare_tour": session.get('has_seen_compare_tour', 0),
                    "has_min_turnus": has_min_turnus,
                }
            finally:
                db_session.close()
        return {"has_seen_tour": 0, "has_seen_favorites_tour": 0, "has_seen_mintur_tour": 0, "has_seen_compare_tour": 0, "has_min_turnus": False}

    from app.routes.main import blueprints

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
