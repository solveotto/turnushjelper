from flask import Blueprint

admin = Blueprint("admin", __name__, url_prefix="/admin")

from app.routes.admin import (  # noqa: E402, F401
    dashboard,
    emails,
    employees,
    turnus,
    users,
)
