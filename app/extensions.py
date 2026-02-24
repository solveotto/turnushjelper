from threading import Lock

from flask_caching import Cache
from flask_login import LoginManager
from flask_mail import Mail

cache = Cache(config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 3600,
    'CACHE_THRESHOLD': 300,   # max entries before LRU eviction (prevents unbounded memory growth)
})
login_manager = LoginManager()
mail = Mail()
favorite_lock = Lock()
