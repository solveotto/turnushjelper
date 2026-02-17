import logging
import os
from logging.handlers import RotatingFileHandler

from app.extensions import favorite_lock  # noqa: F401
from app.routes.admin import admin
from app.routes.api import api

# Import all Blueprints
from app.routes.auth import auth
from app.routes.downloads import downloads
from app.routes.minside import minside
from app.routes.registration import registration
from app.routes.shifts import shifts
from app.utils import df_utils
from config import AppConfig


# Global variables that need to be shared across Blueprints
df_manager = df_utils.DataframeManager()

# Configure logging
os.makedirs(AppConfig.log_dir, exist_ok=True)
log_file_path = os.path.join(AppConfig.log_dir, "app.log")
rotating_handler = RotatingFileHandler(
    log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5
)
rotating_handler.setLevel(logging.WARNING)
rotating_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s")
)

logging.basicConfig(
    level=logging.WARNING, handlers=[rotating_handler, logging.StreamHandler()]
)


# List of all Blueprints to register
blueprints = [auth, shifts, admin, api, downloads, minside, registration]
