from threading import Lock

from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

# SimpleCache is per-process and production runs 2 gunicorn workers, so an
# invalidation only reaches the worker that served the admin request. Accepted
# trade-off (see Task 2.1 in TODO_forensic_audit.md): admin imports are rare
# and a service restart clears every worker. Switch CACHE_TYPE to RedisCache
# if workers ever scale past 2 or invalidation becomes user-triggered.
cache = Cache(config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 3600,
    'CACHE_THRESHOLD': 300,   # max entries before LRU eviction (prevents unbounded memory growth)
})
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # no global default — apply per-route
    storage_uri="memory://",
)
login_manager = LoginManager()
mail = Mail()
# Serializes favorite add/reorder within a worker. The real guard against
# duplicate favorites is the DB UniqueConstraint on
# (user_id, shift_title, turnus_set_id) in models.py — that holds across
# workers. This lock only keeps order_index assignment (max + 1) from
# colliding between threads; a cross-worker collision is possible but purely
# cosmetic and self-corrects on the user's next reorder.
favorite_lock = Lock()
