import importlib.util
import sys
import types
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path
project_root = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, project_root)

from config import get_database_uri  # noqa: E402


def _load_module_from_file(name, filepath):
    """Load a Python module directly from file, bypassing package __init__.py."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register a bare 'app' package so child imports don't trigger app/__init__.py
sys.modules["app"] = types.ModuleType("app")

# Stub out flask_login.UserMixin (models.py imports it at module level)
_flask_login_stub = types.ModuleType("flask_login")
_flask_login_stub.UserMixin = type("UserMixin", (), {})
sys.modules["flask_login"] = _flask_login_stub

# Stub out bcrypt (models.py imports it)
_bcrypt_stub = types.ModuleType("bcrypt")
_bcrypt_stub.checkpw = lambda *a: False
_bcrypt_stub.hashpw = lambda *a: b""
_bcrypt_stub.gensalt = lambda: b""
sys.modules["bcrypt"] = _bcrypt_stub

# Stub out app.extensions with a minimal mock (models.py imports 'cache' from it)
_ext_stub = types.ModuleType("app.extensions")
_ext_stub.cache = type("FakeCache", (), {"get": lambda *a: None, "set": lambda *a: None})()
_ext_stub.login_manager = None
_ext_stub.mail = None
_ext_stub.favorite_lock = None
sys.modules["app.extensions"] = _ext_stub

# Stub out app.services.user_service (models.py lazily imports from it)
sys.modules["app.services"] = types.ModuleType("app.services")
_svc_stub = types.ModuleType("app.services.user_service")
sys.modules["app.services.user_service"] = _svc_stub

# Load app.database (defines Base, engine)
_load_module_from_file("app.database", Path(project_root) / "app" / "database.py")
from app.database import Base  # noqa: E402

# Load app.models (registers all ORM models with Base.metadata)
_load_module_from_file("app.models", Path(project_root) / "app" / "models.py")

# ── Alembic configuration ───────────────────────────────────────────
config = context.config
config.set_main_option("sqlalchemy.url", get_database_uri())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to DB and applies changes)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
