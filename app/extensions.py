from threading import Lock

from flask_caching import Cache
from flask_login import LoginManager
from flask_mail import Mail

cache = Cache(config={'CACHE_TYPE': 'simple'})
login_manager = LoginManager()
mail = Mail()
favorite_lock = Lock()
