import logging

from flask import Flask, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user

from app.database import get_db_session
from app.extensions import cache, csrf, limiter, login_manager, mail
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
    csrf.init_app(app)
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

    # Configure SQLAlchemy-backed session storage
    from app.utils.sa_session_interface import SqlAlchemySessionInterface
    app.session_interface = SqlAlchemySessionInterface()

    @app.context_processor
    def inject_tour_state():
        if current_user.is_authenticated:
            from app.models import Innplassering, TurnusSet
            from app.utils.pdf_downloads import get_pdf_downloads
            from app.utils.turnus_helpers import get_user_turnus_set
            from flask import url_for

            # Tour flags — read from DB columns, cached 60s per user.
            # Only one key differs from the old session key name:
            # has_seen_tour → has_seen_turnusliste_tour (DB column).
            tour_cache_key = f"tour_state_{current_user.id}"
            tour_state = cache.get(tour_cache_key)
            if tour_state is None:
                db_session = get_db_session()
                try:
                    db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
                    if db_user:
                        tour_state = {
                            "has_seen_tour": db_user.has_seen_turnusliste_tour or 0,
                            "has_seen_favorites_tour": db_user.has_seen_favorites_tour or 0,
                            "has_seen_mintur_tour": db_user.has_seen_mintur_tour or 0,
                            "has_seen_compare_tour": db_user.has_seen_compare_tour or 0,
                            "has_seen_welcome": db_user.has_seen_welcome or 0,
                            "has_seen_soknadsskjema_tour": db_user.has_seen_soknadsskjema_tour or 0,
                        }
                    else:
                        tour_state = {
                            "has_seen_tour": 0, "has_seen_favorites_tour": 0,
                            "has_seen_mintur_tour": 0, "has_seen_compare_tour": 0,
                            "has_seen_welcome": 0, "has_seen_soknadsskjema_tour": 0,
                        }
                finally:
                    db_session.close()
                cache.set(tour_cache_key, tour_state, timeout=60)

            # has_min_turnus — cached 60s per user.
            min_turnus_key = f"has_min_turnus_{current_user.id}"
            has_min_turnus = cache.get(min_turnus_key)
            if has_min_turnus is None:
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
                finally:
                    db_session.close()
                cache.set(min_turnus_key, has_min_turnus, timeout=60)

            # PDF downloads — cached per turnus set.
            turnus_set = get_user_turnus_set()
            pdf_downloads = []
            if turnus_set:
                year_id = turnus_set["year_identifier"].lower()
                pdf_cache_key = f"pdf_downloads_{year_id}"
                pdf_downloads = cache.get(pdf_cache_key)
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
                    cache.set(pdf_cache_key, pdf_downloads, timeout=300)

            return {
                **tour_state,
                "has_min_turnus": has_min_turnus,
                "pdf_downloads": pdf_downloads,
                "global_turnus_set": turnus_set,
            }
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

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.headers.get('X-CSRFToken'):
            # API call via apiFetch — return JSON so the client can reload silently
            return jsonify({'status': 'error', 'code': 'csrf_expired'}), 400
        flash('Sesjonen din har utløpt, prøv igjen.', 'warning')
        return redirect(request.referrer or url_for('shifts.turnusliste'))

    from app.routes.main import blueprints

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
