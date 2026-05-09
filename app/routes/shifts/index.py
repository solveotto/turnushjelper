from flask import redirect, url_for
from flask_login import login_required

from app.routes.shifts import shifts


@shifts.route("/")
@login_required
def index():
    from config import AppConfig

    landing = AppConfig.LANDING_PAGE or "mintur"
    return redirect(url_for(f"shifts.{landing}"))
