"""Email from admins to all users: who gets it, the draft, and the send.

The send runs as its own process (scripts/send_broadcast_email.py). It is one
Mailgun call per person and each can take 10 s, which a gunicorn worker would
not survive. Its state lives in the database, so a poll can land on either
worker and a restart leaves enough behind to carry on.

That process has no Flask app context, so nothing here may use render_template
or url_for: templates go through a plain jinja2 environment, and the request
passes its base URL along.
"""

import fcntl
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime

import jinja2
from itsdangerous import BadSignature, URLSafeSerializer
from markupsafe import Markup, escape
from sqlalchemy import func

from app.database import get_db_session
from app.models import BroadcastEmail, BroadcastRecipient, DBUser
from app.services.feedback_service import SUPPORT_EMAIL
from app.utils import email_utils
from config import AppConfig

logger = logging.getLogger(__name__)

DRAFT = "draft"
SENDING = "sending"
STOPPED = "stopped"
DONE = "done"
CLOSED = "closed"

PENDING = "pending"
IN_FLIGHT = "sending"
SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"
UNKNOWN = "unknown"

MODE_OFF = "off"
MODE_LIST = "list"
MODE_ALL = "all"

MAX_SUBJECT_CHARS = 200
MAX_BODY_CHARS = 20000
MAX_FAILURES_IN_A_ROW = 5
SEND_PAUSE_SECONDS = 0.2

LOCK_NAME = "broadcast_email.lock"
LOG_NAME = "broadcast_email.log"
LOCK_WAIT_SECONDS = 5
# Between start() marking a send as running and its process taking the lock.
START_GRACE_SECONDS = 60

NOT_FOUND = "Fant ikke e-posten."
SENDING_OFF = "Utsending er slått av på denne serveren."
SOMETHING_WENT_WRONG = "Noe gikk galt. Se loggen."

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "send_broadcast_email.py",
)

_ADDRESS_RE = re.compile(r"[^@\s]+@[^@\s]+")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

_templates = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "emails")
    ),
    autoescape=jinja2.select_autoescape(enabled_extensions=("html",), default=False),
)


# ── Who gets it ────────────────────────────────────────────────────────


def recipient_mode():
    """The server's BROADCAST_RECIPIENTS setting as (mode, addresses)."""
    value = (AppConfig.BROADCAST_RECIPIENTS or "").strip()
    if not value:
        return MODE_OFF, []
    if value.lower() == "all":
        return MODE_ALL, []
    return MODE_LIST, [a.strip().lower() for a in value.split(",") if a.strip()]


def eligible_users_query(db_session):
    """Accounts that can log in, have a real address and haven't opted out.

    A registered account isn't enough: create_user() stores the username as the
    email, and drivers flagged as not on the NLF list are locked out.
    """
    return db_session.query(DBUser).filter(
        func.coalesce(DBUser.is_stub, 0) == 0,
        DBUser.email_verified == 1,
        DBUser.email.like("%_@_%"),
        func.coalesce(DBUser.not_on_nlf_list, 0) == 0,
        DBUser.announcements_opt_out == 0,
        DBUser.username != "testbruker",
    )


def eligible_recipients(db_session):
    """Eligible users narrowed by the server's mode, one per address."""
    mode, addresses = recipient_mode()
    seen = set()
    recipients = []
    for user in eligible_users_query(db_session).order_by(DBUser.id):
        address = user.email.lower()
        if address in seen or (mode == MODE_LIST and address not in addresses):
            continue
        seen.add(address)
        recipients.append(user)
    return recipients


def recipient_count():
    db_session = get_db_session()
    try:
        return len(eligible_recipients(db_session))
    finally:
        db_session.close()


def _still_eligible(db_session, user_id):
    """The user, if they may still get this send. Honours an unsubscribe, a
    deleted account or a narrowed server setting since the snapshot."""
    user = eligible_users_query(db_session).filter(DBUser.id == user_id).first()
    if user is None:
        return None
    mode, addresses = recipient_mode()
    if mode == MODE_OFF or (mode == MODE_LIST and user.email.lower() not in addresses):
        return None
    return user


# ── Unsubscribing ──────────────────────────────────────────────────────


def _serializer():
    return URLSafeSerializer(AppConfig.SECRET_KEY, salt="email-opt-out")


def unsubscribe_token(user_id):
    return _serializer().dumps(user_id)


def user_id_from_token(token):
    try:
        value = _serializer().loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def unsubscribe_url(base_url, user_id):
    return f"{base_url.rstrip('/')}/minside/avmeld/{unsubscribe_token(user_id)}"


def set_opt_out(user_id, opted_out):
    """Set the opt-out on every account with this user's address, since only one
    of them gets each email. False if the user doesn't exist."""
    value = 1 if opted_out else 0
    db_session = get_db_session()
    try:
        user = db_session.get(DBUser, user_id)
        if user is None:
            return False
        if user.email:
            db_session.query(DBUser).filter(func.lower(DBUser.email) == user.email.lower()).update(
                {DBUser.announcements_opt_out: value}, synchronize_session=False
            )
        else:
            user.announcements_opt_out = value
        db_session.commit()
        return True
    except Exception:
        db_session.rollback()
        logger.exception("Could not set opt-out for user %s", user_id)
        return False
    finally:
        db_session.close()


def is_opted_out(user_id):
    """True or False, or None if the user doesn't exist."""
    db_session = get_db_session()
    try:
        user = db_session.get(DBUser, user_id)
        return bool(user.announcements_opt_out) if user else None
    finally:
        db_session.close()


# ── The email itself ───────────────────────────────────────────────────


def _linkified(line):
    parts = []
    position = 0
    for match in _URL_RE.finditer(line):
        url = match.group(0).rstrip(".,;:!?)")
        parts.append(escape(line[position:match.start()]))
        parts.append(Markup('<a href="{0}">{0}</a>').format(url))
        position = match.start() + len(url)
    parts.append(escape(line[position:]))
    return Markup("").join(parts)


def _body_html(body):
    paragraphs = re.split(r"\n\s*\n", body.strip())
    return Markup("\n").join(
        Markup("<p>{}</p>").format(Markup("<br>").join(_linkified(line) for line in paragraph.split("\n")))
        for paragraph in paragraphs
    )


def render_email(subject, body, unsubscribe_link):
    """The email as (text, html)."""
    text = _templates.get_template("announcement.txt").render(
        body=body, unsubscribe_url=unsubscribe_link
    )
    html = _templates.get_template("announcement.html").render(
        subject=subject, body_html=_body_html(body), unsubscribe_url=unsubscribe_link
    )
    return text, html


def _deliver(address, subject, text, html, unsubscribe_link):
    return email_utils.send_mailgun_email(
        address, subject, text, html,
        reply_to=SUPPORT_EMAIL,
        headers={"List-Unsubscribe": f"<{unsubscribe_link}>"},
    )


# ── Draft ──────────────────────────────────────────────────────────────


def _cleaned_text(subject, body):
    """(subject, body, error). The subject ends up in a mail header, so
    whitespace including newlines collapses to single spaces."""
    subject = " ".join((subject or "").split())
    body = (body or "").replace("\r\n", "\n").strip()
    if not subject:
        return None, None, "Emne mangler."
    if len(subject) > MAX_SUBJECT_CHARS:
        return None, None, f"Emnet kan ha maks {MAX_SUBJECT_CHARS} tegn."
    if not body:
        return None, None, "Tekst mangler."
    if len(body) > MAX_BODY_CHARS:
        return None, None, f"Teksten kan ha maks {MAX_BODY_CHARS} tegn."
    return subject, body, None


def create_draft(subject, body, user_id):
    """Returns (ok, message, broadcast_id)."""
    subject, body, error = _cleaned_text(subject, body)
    if error:
        return False, error, None
    db_session = get_db_session()
    try:
        broadcast = BroadcastEmail(subject=subject, body=body, state=DRAFT, created_by_id=user_id)
        db_session.add(broadcast)
        db_session.commit()
        return True, "Utkastet er lagret.", broadcast.id
    except Exception:
        db_session.rollback()
        logger.exception("Could not save broadcast draft")
        return False, SOMETHING_WENT_WRONG, None
    finally:
        db_session.close()


def update_text(broadcast_id, subject, body):
    """Change the text of a draft or a stopped send. Always requires a new test."""
    subject, body, error = _cleaned_text(subject, body)
    if error:
        return False, error
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None:
            return False, NOT_FOUND
        if _effective_state(broadcast) not in (DRAFT, STOPPED):
            return False, "Teksten kan bare endres på et utkast eller en stoppet utsending."
        broadcast.subject = subject
        broadcast.body = body
        broadcast.test_sent_at = None
        db_session.commit()
        return True, "Teksten er lagret. Send en ny test før du sender."
    except Exception:
        db_session.rollback()
        logger.exception("Could not update broadcast %s", broadcast_id)
        return False, SOMETHING_WENT_WRONG
    finally:
        db_session.close()


def send_test(broadcast_id, address, user_id, base_url):
    """Send to one address, in the request. Unlocks sending if it succeeds. The
    unsubscribe link is the sending admin's own."""
    address = (address or "").strip()
    if not _ADDRESS_RE.fullmatch(address):
        return False, "Skriv inn en gyldig e-postadresse."
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None:
            return False, NOT_FOUND
        if _effective_state(broadcast) not in (DRAFT, STOPPED):
            return False, "Kan bare teste et utkast eller en stoppet utsending."
        link = unsubscribe_url(base_url, user_id)
        text, html = render_email(broadcast.subject, broadcast.body, link)
        if not _deliver(address, f"[TEST] {broadcast.subject}", text, html, link):
            return False, "Kunne ikke sende testen."
        broadcast.test_sent_at = datetime.now()
        db_session.commit()
        return True, f"Testen er sendt til {address}."
    except Exception:
        db_session.rollback()
        logger.exception("Could not send test of broadcast %s", broadcast_id)
        return False, SOMETHING_WENT_WRONG
    finally:
        db_session.close()


# ── Starting and following a send ──────────────────────────────────────


@contextmanager
def _lock(wait_seconds=0.0):
    """Yield True while holding the send lock, False if another process has it.

    The OS drops it when the process dies, so a killed send can't leave it stuck.
    """
    os.makedirs(AppConfig.log_dir, exist_ok=True)
    with open(os.path.join(AppConfig.log_dir, LOCK_NAME), "w") as f:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.1)
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def is_running():
    with _lock() as acquired:
        return not acquired


def _started_recently(broadcast):
    if broadcast.started_at is None:
        return False
    return (datetime.now() - broadcast.started_at).total_seconds() < START_GRACE_SECONDS


def _effective_state(broadcast):
    """The stored state, except that a send whose process is gone is stopped."""
    if broadcast.state != SENDING or _started_recently(broadcast) or is_running():
        return broadcast.state
    return STOPPED


def _send_in_progress(db_session):
    if is_running():
        return True
    return any(
        _started_recently(broadcast)
        for broadcast in db_session.query(BroadcastEmail).filter_by(state=SENDING)
    )


def _close_other_sends(db_session, broadcast_id):
    """Only one send can be carried on, so starting one gives up on any other."""
    others = db_session.query(BroadcastEmail).filter(
        BroadcastEmail.id != broadcast_id,
        BroadcastEmail.state.in_((STOPPED, SENDING)),
    )
    for other in others:
        other.state = CLOSED
        other.finished_at = datetime.now()
        db_session.query(BroadcastRecipient).filter_by(broadcast_id=other.id).delete()


def _claim_send(broadcast_id, user_id, typed_count):
    """Check that the send may start and mark it as running. Returns (ok, message)."""
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None:
            return False, NOT_FOUND
        if _send_in_progress(db_session):
            return False, "En utsending kjører allerede."
        state = _effective_state(broadcast)
        if state not in (DRAFT, STOPPED):
            return False, "Denne e-posten kan ikke sendes."
        if broadcast.test_sent_at is None:
            return False, "Send en test først."

        recipients = []
        if state == DRAFT:
            recipients = eligible_recipients(db_session)
            if not recipients:
                return False, "Ingen mottakere."
            if typed_count != len(recipients):
                return False, f"Antallet stemmer ikke. Det er nå {len(recipients)} mottakere."

        # Conditional, so a double click or two admins can't both claim it.
        claimed = db_session.query(BroadcastEmail).filter(
            BroadcastEmail.id == broadcast_id,
            BroadcastEmail.state == broadcast.state,
            BroadcastEmail.started_at == broadcast.started_at,
        ).update({
            BroadcastEmail.state: SENDING,
            BroadcastEmail.stop_requested: 0,
            BroadcastEmail.stop_reason: None,
            BroadcastEmail.sent_by_id: user_id,
            BroadcastEmail.started_at: datetime.now(),
            BroadcastEmail.finished_at: None,
        }, synchronize_session=False)
        if claimed != 1:
            db_session.rollback()
            return False, "En utsending kjører allerede."

        if state == DRAFT:
            broadcast.total_count = len(recipients)
            db_session.add_all(
                BroadcastRecipient(broadcast_id=broadcast_id, user_id=user.id, state=PENDING)
                for user in recipients
            )
        _close_other_sends(db_session, broadcast_id)
        db_session.commit()
        return True, "Utsendingen er startet."
    except Exception:
        db_session.rollback()
        logger.exception("Could not start broadcast %s", broadcast_id)
        return False, SOMETHING_WENT_WRONG
    finally:
        db_session.close()


def _spawn(broadcast_id, base_url):
    os.makedirs(AppConfig.log_dir, exist_ok=True)
    with open(os.path.join(AppConfig.log_dir, LOG_NAME), "a") as log_file:
        # Its own session, so the process outlives the request and is not tied
        # to the gunicorn worker. A service restart still stops it.
        subprocess.Popen(
            [sys.executable, SCRIPT, "--id", str(broadcast_id), "--base-url", base_url],
            cwd=os.path.dirname(os.path.dirname(SCRIPT)),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def start(broadcast_id, user_id, base_url, typed_count=None):
    """Start the send, or carry on with a stopped one. Returns (ok, message).

    Only a first send takes a recipient count, since a stopped one already has
    its recipients.
    """
    if recipient_mode()[0] == MODE_OFF:
        return False, SENDING_OFF
    ok, message = _claim_send(broadcast_id, user_id, typed_count)
    if not ok:
        return False, message
    try:
        _spawn(broadcast_id, base_url)
    except OSError:
        logger.exception("Could not spawn the send of broadcast %s", broadcast_id)
        _stop(broadcast_id, "Kunne ikke starte utsendingen.")
        return False, "Kunne ikke starte utsendingen."
    return True, message


def request_stop(broadcast_id):
    """Ask a running send to stop before its next recipient."""
    db_session = get_db_session()
    try:
        updated = db_session.query(BroadcastEmail).filter_by(id=broadcast_id, state=SENDING).update(
            {BroadcastEmail.stop_requested: 1}, synchronize_session=False
        )
        db_session.commit()
        if not updated:
            return False, "Utsendingen kjører ikke."
        return True, "Utsendingen stopper før neste mottaker."
    except Exception:
        db_session.rollback()
        logger.exception("Could not stop broadcast %s", broadcast_id)
        return False, SOMETHING_WENT_WRONG
    finally:
        db_session.close()


def close(broadcast_id):
    """Give up on the rest of a stopped send. The counts stay, the recipients go."""
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None:
            return False, NOT_FOUND
        if _effective_state(broadcast) != STOPPED:
            return False, "Bare en stoppet utsending kan avsluttes."
        broadcast.state = CLOSED
        broadcast.finished_at = datetime.now()
        db_session.query(BroadcastRecipient).filter_by(broadcast_id=broadcast_id).delete()
        db_session.commit()
        return True, "Utsendingen er avsluttet."
    except Exception:
        db_session.rollback()
        logger.exception("Could not close broadcast %s", broadcast_id)
        return False, SOMETHING_WENT_WRONG
    finally:
        db_session.close()


def _usernames(db_session, user_ids):
    ids = {user_id for user_id in user_ids if user_id}
    if not ids:
        return {}
    rows = db_session.query(DBUser.id, DBUser.username).filter(DBUser.id.in_(ids))
    return {row.id: row.username for row in rows}


def _as_dict(db_session, broadcast, usernames):
    state = _effective_state(broadcast)
    reason = broadcast.stop_reason
    if state != broadcast.state:
        reason = "Utsendingen stoppet uventet."
    remaining = db_session.query(func.count(BroadcastRecipient.id)).filter_by(
        broadcast_id=broadcast.id, state=PENDING
    ).scalar()
    return {
        "id": broadcast.id,
        "subject": broadcast.subject,
        "body": broadcast.body,
        "state": state,
        "reason": reason,
        "stop_requested": bool(broadcast.stop_requested),
        "test_sent": broadcast.test_sent_at is not None,
        "created_by": usernames.get(broadcast.created_by_id),
        "created_at": broadcast.created_at,
        "sent_by": usernames.get(broadcast.sent_by_id),
        "started_at": broadcast.started_at,
        "finished_at": broadcast.finished_at,
        "total": broadcast.total_count,
        "sent": broadcast.sent_count,
        "failed": broadcast.failed_count,
        "skipped": broadcast.skipped_count,
        "unknown": broadcast.unknown_count,
        "remaining": remaining,
    }


def get_broadcast(broadcast_id):
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None:
            return None
        usernames = _usernames(db_session, [broadcast.created_by_id, broadcast.sent_by_id])
        return _as_dict(db_session, broadcast, usernames)
    finally:
        db_session.close()


def get_status(broadcast_id):
    """What the page polls. The text is left out, since it never changes mid-send."""
    broadcast = get_broadcast(broadcast_id)
    if broadcast is None:
        return None
    keys = ("state", "reason", "stop_requested", "total", "sent", "failed", "skipped", "unknown", "remaining")
    return {key: broadcast[key] for key in keys}


def list_broadcasts():
    """Every email, newest first."""
    db_session = get_db_session()
    try:
        broadcasts = db_session.query(BroadcastEmail).order_by(BroadcastEmail.id.desc()).all()
        user_ids = [b.created_by_id for b in broadcasts] + [b.sent_by_id for b in broadcasts]
        usernames = _usernames(db_session, user_ids)
        return [_as_dict(db_session, broadcast, usernames) for broadcast in broadcasts]
    finally:
        db_session.close()


# ── The send itself, in its own process ────────────────────────────────


def _stop(broadcast_id, reason):
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        broadcast.state = STOPPED
        broadcast.stop_requested = 0
        broadcast.stop_reason = reason[:255]
        broadcast.finished_at = datetime.now()
        db_session.commit()
    finally:
        db_session.close()


def _prepare_run(broadcast_id):
    """Sort out what an earlier run left behind. Returns (subject, body), or None
    if this send isn't marked as running.

    Someone still in flight may or may not have got it, and a duplicate is the
    worse mistake, so they aren't tried again.
    """
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if broadcast is None or broadcast.state != SENDING:
            return None
        text = broadcast.subject, broadcast.body
        recipients = db_session.query(BroadcastRecipient).filter_by(broadcast_id=broadcast_id)
        in_flight = recipients.filter_by(state=IN_FLIGHT).update({"state": UNKNOWN}, synchronize_session=False)
        recipients.filter_by(state=FAILED).update({"state": PENDING}, synchronize_session=False)
        broadcast.unknown_count += in_flight
        broadcast.failed_count = 0
        db_session.commit()
        return text
    finally:
        db_session.close()


def _stop_requested(broadcast_id):
    db_session = get_db_session()
    try:
        return bool(db_session.get(BroadcastEmail, broadcast_id).stop_requested)
    finally:
        db_session.close()


def _next_recipient(broadcast_id):
    """(row_id, user_id, address) of the next one who may still get it, or None.
    Those who no longer may are marked as skipped on the way."""
    db_session = get_db_session()
    try:
        while True:
            row = (
                db_session.query(BroadcastRecipient)
                .filter_by(broadcast_id=broadcast_id, state=PENDING)
                .order_by(BroadcastRecipient.id)
                .first()
            )
            if row is None:
                return None
            user = _still_eligible(db_session, row.user_id)
            if user is not None:
                return row.id, row.user_id, user.email
            row.state = SKIPPED
            db_session.get(BroadcastEmail, broadcast_id).skipped_count += 1
            db_session.commit()
    finally:
        db_session.close()


def _mark_in_flight(row_id):
    db_session = get_db_session()
    try:
        db_session.get(BroadcastRecipient, row_id).state = IN_FLIGHT
        db_session.commit()
    finally:
        db_session.close()


def _record_result(broadcast_id, row_id, delivered):
    db_session = get_db_session()
    try:
        db_session.get(BroadcastRecipient, row_id).state = SENT if delivered else FAILED
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        if delivered:
            broadcast.sent_count += 1
        else:
            broadcast.failed_count += 1
        db_session.commit()
    finally:
        db_session.close()


def _finish(broadcast_id):
    """Done if nobody failed, and then the recipients are no longer needed.
    Returns the exit code."""
    db_session = get_db_session()
    try:
        broadcast = db_session.get(BroadcastEmail, broadcast_id)
        failed = broadcast.failed_count
        if not failed:
            broadcast.state = DONE
            broadcast.stop_reason = None
            broadcast.finished_at = datetime.now()
            db_session.query(BroadcastRecipient).filter_by(broadcast_id=broadcast_id).delete()
            db_session.commit()
    finally:
        db_session.close()
    if failed:
        noun = "e-post" if failed == 1 else "e-poster"
        _stop(broadcast_id, f"{failed} {noun} kunne ikke sendes.")
        return 1
    return 0


def _send_all(broadcast_id, base_url, log):
    text = _prepare_run(broadcast_id)
    if text is None:
        log(f"Utsending {broadcast_id} er ikke startet.")
        return 1
    subject, body = text
    if recipient_mode()[0] == MODE_OFF:
        _stop(broadcast_id, SENDING_OFF)
        return 1

    failures_in_a_row = 0
    while True:
        if _stop_requested(broadcast_id):
            _stop(broadcast_id, "Stoppet av administrator.")
            return 0
        recipient = _next_recipient(broadcast_id)
        if recipient is None:
            return _finish(broadcast_id)
        row_id, user_id, address = recipient

        link = unsubscribe_url(base_url, user_id)
        text_body, html_body = render_email(subject, body, link)
        _mark_in_flight(row_id)
        delivered = _deliver(address, subject, text_body, html_body, link)
        _record_result(broadcast_id, row_id, delivered)

        failures_in_a_row = 0 if delivered else failures_in_a_row + 1
        if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
            # More likely a quota or credentials problem than bad addresses.
            _stop(broadcast_id, f"Stoppet etter {MAX_FAILURES_IN_A_ROW} feil på rad. Sjekk Mailgun.")
            return 1
        time.sleep(SEND_PAUSE_SECONDS)


def run(broadcast_id, base_url, log=print):
    """Send to everyone still waiting. Returns 0 when done or stopped by an admin,
    1 when it failed, 3 when another send holds the lock."""
    with _lock(wait_seconds=LOCK_WAIT_SECONDS) as acquired:
        if not acquired:
            log("En utsending kjører allerede.")
            return 3
        try:
            code = _send_all(broadcast_id, base_url, log)
            log(f"Utsending {broadcast_id} ferdig med kode {code}.")
            return code
        except Exception as e:
            logger.exception("Broadcast %s failed", broadcast_id)
            log(traceback.format_exc())
            _stop(broadcast_id, f"Uventet feil: {e}")
            return 1
