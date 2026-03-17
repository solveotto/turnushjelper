from threading import Lock

from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail

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
favorite_lock = Lock()
