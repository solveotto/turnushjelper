import logging

from flask import Flask
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
            db_session = get_db_session()
            try:
                db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
                return {
                    "has_seen_tour": db_user.has_seen_turnusliste_tour or 0 if db_user else 0,
                    "has_seen_favorites_tour": db_user.has_seen_favorites_tour or 0 if db_user else 0,
                }
            finally:
                db_session.close()
        return {"has_seen_tour": 0, "has_seen_favorites_tour": 0}

    from app.routes.main import blueprints

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
