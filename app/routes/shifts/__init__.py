import logging

from flask import Blueprint, request
from flask_login import current_user

logger = logging.getLogger(__name__)

shifts = Blueprint("shifts", __name__)

_TRACKED_ENDPOINTS = {"shifts.turnusliste", "shifts.oversikt", "shifts.favorites"}


@shifts.before_request
def log_page_view():
    if not current_user.is_authenticated:
        return
    if request.endpoint not in _TRACKED_ENDPOINTS:
        return
    from app.services.activity_service import log_event

    page = request.endpoint.split(".")[-1]
    log_event(current_user.id, "page_view", details=page)


def _classify_shift_type(start_str: str, end_str: str) -> str:
    """Map shift start/end times to a Norwegian shift-type label.

    Uses a simplified 4-label system intentionally different from the
    5-class color system in shift-classifier.js — all pre-08:00 starts
    are "Tidlig" regardless of whether they start before or after 06:00.
    """
    sh, sm = (int(x) for x in start_str.split(":"))
    eh, em = (int(x) for x in end_str.split(":"))
    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em
    overnight = end_mins < start_mins  # end time wraps past midnight

    if start_mins < 8 * 60:
        return "Tidlig"
    if start_mins < 12 * 60:
        return "Dag"
    if overnight and end_mins >= 4 * 60:
        return "Natt"
    return "Ettermiddag"


from app.routes.shifts import (  # noqa: E402, F401
    favorites,
    index,
    mintur,
    oversikt,
    soknadsskjema,
    turnusnokkel,
    turnusliste,
)
