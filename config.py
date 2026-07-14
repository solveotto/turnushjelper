import os
from datetime import timedelta

from dotenv import load_dotenv

# Load .env file from the same directory as this file (no-op if file doesn't exist)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _env(key, default=None):
    """Get environment variable with optional default."""
    return os.environ.get(key, default)


def _env_int(key, default=0):
    """Get environment variable as integer."""
    return int(os.environ.get(key, default))


def _env_bool(key, default=False):
    """Get environment variable as boolean."""
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


def get_database_uri():
    """Get database URI based on environment variables."""
    db_type = _env("DB_TYPE", "sqlite")

    if db_type == "sqlite":
        sqlite_path = _env("SQLITE_PATH") or "./dummy.db"
        if not os.path.isabs(sqlite_path):
            sqlite_path = os.path.join(os.path.dirname(__file__), sqlite_path)
        return f"sqlite:///{sqlite_path}"

    elif db_type == "mysql":
        host = _env("MYSQL_HOST")
        user = _env("MYSQL_USER")
        password = _env("MYSQL_PASSWORD")
        database = _env("MYSQL_DATABASE")
        return f"mysql+pymysql://{user}:{password}@{host}/{database}?charset=utf8mb4"

    else:
        raise ValueError(f"Unsupported database type: {db_type}")


class AppConfig:
    SECRET_KEY = _env("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in .env or environment")

    # Database
    DB_TYPE = _env("DB_TYPE", "sqlite")

    # Session/auth cookie hardening.
    # SESSION_COOKIE_SECURE defaults ON in production (DB_TYPE=mysql) so the
    # session cookie is never transmitted over plaintext HTTP; it stays OFF for
    # local sqlite dev (served over http://localhost, where a Secure cookie
    # would never be sent). Override explicitly via the env var if needed.
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", DB_TYPE == "mysql")
    SESSION_COOKIE_HTTPONLY = _env_bool("SESSION_COOKIE_HTTPONLY", True)
    SESSION_COOKIE_SAMESITE = _env("SESSION_COOKIE_SAMESITE", "Lax")
    # Flask-Login "remember me" cookie (currently unused; hardened for defense).
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE

    # Reverse-proxy trust. In production the app runs behind nginx, which
    # forwards the real client IP and scheme in X-Forwarded-* headers. ProxyFix
    # (wired in create_app) trusts exactly this many proxy hops so the rate
    # limiter sees real client IPs and url_for(_external=True) builds https
    # links. Defaults to 1 in production (single nginx) and 0 in dev (no proxy —
    # it MUST stay off there, or a forged X-Forwarded-For could spoof the client
    # IP). Set to 2 if a CDN (e.g. Cloudflare) sits in front of nginx.
    TRUSTED_PROXY_COUNT = _env_int(
        "TRUSTED_PROXY_COUNT", 1 if DB_TYPE == "mysql" else 0
    )

    # Email — Mailgun (primary)
    MAILGUN_API_KEY = _env("MAILGUN_API_KEY", "")
    MAILGUN_DOMAIN = _env("MAILGUN_DOMAIN", "mail.turnushjelper.no")
    MAILGUN_REGION = _env("MAILGUN_REGION", "eu")
    SENDER_EMAIL = _env("SENDER_EMAIL", "noreply@mail.turnushjelper.no")
    SENDER_NAME = _env("SENDER_NAME", "Turnushjelper")

    # Email — SMTP (backup, optional)
    SMTP_SERVER = _env("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = _env_int("SMTP_PORT", 587)
    SMTP_USE_TLS = _env_bool("SMTP_USE_TLS", True)
    SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)
    SMTP_USERNAME = _env("SMTP_USERNAME", "")
    SMTP_PASSWORD = _env("SMTP_PASSWORD", "")

    # Verification settings
    TOKEN_EXPIRY_HOURS = _env_int("TOKEN_EXPIRY_HOURS", 48)
    UNVERIFIED_CLEANUP_DAYS = _env_int("UNVERIFIED_CLEANUP_DAYS", 14)
    MAX_VERIFICATION_EMAILS_PER_DAY = _env_int("MAX_VERIFICATION_EMAILS_PER_DAY", 3)

    # MySQL (exposed as class attrs for backup scripts)
    MYSQL_HOST = _env("MYSQL_HOST", "")
    MYSQL_USER = _env("MYSQL_USER", "")
    MYSQL_PASSWORD = _env("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = _env("MYSQL_DATABASE", "")

    # Default admin bootstrap (optional, first-time setup only).
    # SECURITY: there is deliberately NO default password. When
    # DEFAULT_ADMIN_PASSWORD is unset (or trivially weak), init_default_admin()
    # skips auto-provisioning instead of creating a guessable admin/admin
    # account. Set a strong value in the environment to bootstrap an admin.
    DEFAULT_ADMIN_USERNAME = _env("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = _env("DEFAULT_ADMIN_PASSWORD", "")

    PERMANENT_SESSION_LIFETIME = timedelta(days=_env_int("SESSION_LIFETIME_DAYS", 30))

    # Landing page: "mintur" shows Min Turnus, "turnusliste" redirects to /turnusliste
    LANDING_PAGE = _env("LANDING_PAGE", "turnusliste")

    # Paths
    base_dir = os.path.dirname(__file__)
    static_dir = os.path.abspath(os.path.join(base_dir, "app", "static"))
    utils_dir = os.path.abspath(os.path.join(base_dir, "app", "utils"))
    sessions_dir = os.path.abspath(os.path.join(base_dir, "app", "utils", "sessions"))
    log_dir = os.path.abspath(os.path.join(base_dir, "app", "logs"))
    turnusfiler_dir = os.path.abspath(
        os.path.join(base_dir, "app", "static", "turnusfiler")
    )
