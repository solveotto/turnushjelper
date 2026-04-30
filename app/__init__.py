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
            from app.utils.pdf_downloads import get_pdf_downloads
            from app.utils.turnus_helpers import get_user_turnus_set
            from flask import url_for
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

                turnus_set = get_user_turnus_set()
                pdf_downloads = []
                if turnus_set:
                    year_id = turnus_set["year_identifier"].lower()
                    cache_key = f"pdf_downloads_{year_id}"
                    pdf_downloads = cache.get(cache_key)
                    if pdf_downloads is None:
                        raw = get_pdf_downloads(AppConfig.turnusfiler_dir, year_id)
                        pdf_downloads = [
                            {
                                "display_name": item["display_name"],
                                "url": url_for(
                                    "static",
                                    filename=f'turnusfiler/{year_id}/pdf/{item["filename"]}',
                                ),
                            }
                            for item in raw
                        ]
                        cache.set(cache_key, pdf_downloads, timeout=300)

                return {
                    "has_seen_tour": session.get('has_seen_tour', 0),
                    "has_seen_favorites_tour": session.get('has_seen_favorites_tour', 0),
                    "has_seen_mintur_tour": session.get('has_seen_mintur_tour', 0),
                    "has_seen_compare_tour": session.get('has_seen_compare_tour', 0),
                    "has_seen_welcome": session.get('has_seen_welcome', 0),
                    "has_seen_soknadsskjema_tour": session.get('has_seen_soknadsskjema_tour', 0),
                    "has_min_turnus": has_min_turnus,
                    "pdf_downloads": pdf_downloads,
                    "global_turnus_set": turnus_set,
                }
            finally:
                db_session.close()
        return {
            "has_seen_tour": 0,
            "has_seen_favorites_tour": 0,
            "has_seen_mintur_tour": 0,
            "has_seen_compare_tour": 0,
            "has_seen_welcome": 0,
            "has_seen_soknadsskjema_tour": 0,
            "has_min_turnus": False,
            "pdf_downloads": [],
            "global_turnus_set": None,
        }

    @app.template_filter('display_name')
    def display_name_filter(s):
        return s.replace('_', ' ') if s else s

    from app.routes.main import blueprints

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
