"""Email from admins to all users.

Sending to about 400 real people can't be undone, so these tests pin what would
make it go wrong even if the code "works": a driver emailed twice, an unsubscribe
ignored, a locked-out account emailed, or real drivers emailed from staging,
which is a copy of production. Only the Mailgun HTTP call is faked.
"""

import fcntl
import importlib.util
import os
import re
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models import BroadcastEmail, BroadcastRecipient, DBUser

# Before any test patches get_db_session: a module first imported inside a test
# keeps that test's closed connection for the rest of the run (see patch_db).
from app.routes import admin as _admin, minside as _minside  # noqa: F401
from app.routes.shifts import mintur as _mintur  # noqa: F401
from app.services import broadcast_email_service as svc
from tests.conftest import login_user

BASE_URL = "https://example.test/"


class FakeMailgun:
    """Stands in for the Mailgun HTTP API and records what it was given."""

    def __init__(self):
        self.sent = []
        self.failing = set()
        self.on_send = None

    def post(self, url, auth=None, data=None, timeout=None):
        self.sent.append(data)
        if self.on_send:
            self.on_send(data)
        response = MagicMock()
        response.status_code = 500 if data["to"] in self.failing else 200
        response.text = ""
        return response

    @property
    def recipients(self):
        return [data["to"] for data in self.sent]


class Killed(BaseException):
    """A process dying mid-send: no except or cleanup in the job gets to run."""


@pytest.fixture(autouse=True)
def mailgun(monkeypatch):
    """Autouse: no test in this file can reach the real Mailgun."""
    fake = FakeMailgun()
    monkeypatch.setattr("app.utils.email_utils.requests.post", fake.post)
    return fake


@pytest.fixture(autouse=True)
def job_env(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.AppConfig, "log_dir", str(tmp_path))
    monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "all")
    monkeypatch.setattr(svc, "SEND_PAUSE_SECONDS", 0)
    monkeypatch.setattr(svc, "LOCK_WAIT_SECONDS", 0)
    return tmp_path


@pytest.fixture()
def popen_calls(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))
            self.pid = 4242

    monkeypatch.setattr(svc.subprocess, "Popen", FakePopen)
    return calls


@pytest.fixture()
def held_lock(job_env):
    """Another send holding the lock, as a live process would."""
    f = open(job_env / svc.LOCK_NAME, "w")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    yield
    f.close()


def add_user(db_session, username, email, **overrides):
    fields = {
        "password": "x", "is_auth": 0, "email_verified": 1, "is_stub": 0,
        "not_on_nlf_list": 0, "announcements_opt_out": 0,
    }
    fields.update(overrides)
    user = DBUser(username=username, email=email, **fields)
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture()
def admin_id(db_session, patch_db):
    return add_user(db_session, "sjef", "sjef@example.com", is_auth=1)


def tested_draft(admin_id, subject="Nyhet", body="Tekst", mailgun=None):
    ok, message, broadcast_id = svc.create_draft(subject, body, admin_id)
    assert ok, message
    ok, message = svc.send_test(broadcast_id, "sjef@example.com", admin_id, BASE_URL)
    assert ok, message
    if mailgun:
        mailgun.sent.clear()
    return broadcast_id


def start_send(admin_id, mailgun, subject="Nyhet", body="Tekst"):
    broadcast_id = tested_draft(admin_id, subject, body, mailgun)
    ok, message = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())
    assert ok, message
    return broadcast_id


def resume(broadcast_id, admin_id):
    ok, message = svc.start(broadcast_id, admin_id, BASE_URL)
    assert ok, message
    return svc.run(broadcast_id, BASE_URL, log=lambda _: None)


def run(broadcast_id):
    return svc.run(broadcast_id, BASE_URL, log=lambda _: None)


def row_states(db_session, broadcast_id):
    rows = db_session.execute(
        select(BroadcastRecipient.state).where(BroadcastRecipient.broadcast_id == broadcast_id)
    )
    return sorted(state for (state,) in rows)


def age_start(db_session, broadcast_id):
    """Move the send's start past the grace period, as if time had passed."""
    db_session.expire_all()
    db_session.get(BroadcastEmail, broadcast_id).started_at = datetime.now() - timedelta(minutes=5)
    db_session.commit()


class TestRecipients:
    @pytest.mark.parametrize("overrides", [
        {"is_stub": 1},
        {"email_verified": 0},
        {"email": None},
        {"email": "adminbruker"},
        {"not_on_nlf_list": 1},
        {"announcements_opt_out": 1},
    ])
    def test_account_that_should_not_get_email_is_left_out(self, db_session, patch_db, overrides):
        fields = {"email": "x@example.com", **overrides}
        add_user(db_session, "x", **fields)
        add_user(db_session, "ok", "ok@example.com")

        assert [u.username for u in svc.eligible_recipients(db_session)] == ["ok"]

    def test_the_dev_test_user_is_left_out(self, db_session, patch_db):
        add_user(db_session, "testbruker", "testbruker@test.no")

        assert svc.recipient_count() == 0

    @pytest.mark.parametrize("column", ["is_stub", "not_on_nlf_list"])
    def test_null_flag_does_not_silently_drop_a_real_user(self, db_session, patch_db, column):
        add_user(db_session, "x", "x@example.com", **{column: None})

        assert svc.recipient_count() == 1

    def test_same_address_in_different_case_gets_one_email(self, db_session, patch_db):
        first = add_user(db_session, "a", "Same@Example.com")
        add_user(db_session, "b", "same@example.com")

        assert [u.id for u in svc.eligible_recipients(db_session)] == [first]


class TestServerGuard:
    def test_unset_refuses_to_start_and_spawns_nothing(self, admin_id, popen_calls, mailgun, monkeypatch):
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "")
        broadcast_id = tested_draft(admin_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert popen_calls == []

    def test_unset_still_allows_a_test_email(self, admin_id, mailgun, monkeypatch):
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "")
        ok, _, broadcast_id = svc.create_draft("Nyhet", "Tekst", admin_id)

        ok, _ = svc.send_test(broadcast_id, "sjef@example.com", admin_id, BASE_URL)

        assert ok
        assert mailgun.recipients == ["sjef@example.com"]

    def test_job_sends_nothing_if_the_guard_is_off_when_it_runs(
        self, db_session, admin_id, popen_calls, mailgun, monkeypatch
    ):
        broadcast_id = start_send(admin_id, mailgun)
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "")

        assert run(broadcast_id) == 1

        assert mailgun.sent == []
        assert svc.get_status(broadcast_id)["state"] == "stopped"

    def test_list_narrows_recipients_ignoring_case(self, db_session, admin_id, popen_calls, mailgun, monkeypatch):
        add_user(db_session, "a", "a@example.com")
        add_user(db_session, "b", "b@example.com")
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", " B@example.com , nobody@example.com")

        broadcast_id = start_send(admin_id, mailgun)
        run(broadcast_id)

        assert mailgun.recipients == ["b@example.com"]
        assert svc.get_status(broadcast_id)["total"] == 1

    def test_list_narrowed_after_start_is_honoured_by_the_job(
        self, db_session, admin_id, popen_calls, mailgun, monkeypatch
    ):
        add_user(db_session, "a", "a@example.com")
        broadcast_id = start_send(admin_id, mailgun)
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "sjef@example.com")

        run(broadcast_id)

        assert mailgun.recipients == ["sjef@example.com"]

    def test_all_reaches_every_eligible_user(self, db_session, admin_id, popen_calls, mailgun):
        add_user(db_session, "a", "a@example.com")

        run(start_send(admin_id, mailgun))

        assert sorted(mailgun.recipients) == ["a@example.com", "sjef@example.com"]


class TestStart:
    def test_blocked_until_a_test_has_been_sent(self, admin_id, popen_calls):
        _, _, broadcast_id = svc.create_draft("Nyhet", "Tekst", admin_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert popen_calls == []

    def test_a_failed_test_does_not_unlock_sending(self, admin_id, popen_calls, mailgun):
        mailgun.failing.add("sjef@example.com")
        _, _, broadcast_id = svc.create_draft("Nyhet", "Tekst", admin_id)

        ok, _ = svc.send_test(broadcast_id, "sjef@example.com", admin_id, BASE_URL)
        assert not ok

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())
        assert not ok

    def test_editing_after_the_test_requires_a_new_one(self, admin_id, popen_calls, mailgun):
        broadcast_id = tested_draft(admin_id)
        svc.update_text(broadcast_id, "Nyhet", "Ny tekst")

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert popen_calls == []

    @pytest.mark.parametrize("typed", [None, 0, 2, 400])
    def test_wrong_typed_count_is_refused(self, admin_id, popen_calls, mailgun, typed):
        broadcast_id = tested_draft(admin_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=typed)

        assert not ok
        assert popen_calls == []

    def test_count_is_compared_with_the_live_number(self, db_session, admin_id, popen_calls, mailgun):
        broadcast_id = tested_draft(admin_id)
        typed = svc.recipient_count()
        add_user(db_session, "ny", "ny@example.com")

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=typed)

        assert not ok

    def test_no_recipients_is_refused(self, db_session, patch_db, popen_calls, mailgun):
        admin = add_user(db_session, "sjef", "sjef@example.com", is_auth=1, announcements_opt_out=1)
        broadcast_id = tested_draft(admin)

        ok, _ = svc.start(broadcast_id, admin, BASE_URL, typed_count=0)

        assert not ok
        assert popen_calls == []

    def test_double_click_starts_one_job(self, admin_id, popen_calls, mailgun):
        broadcast_id = tested_draft(admin_id)
        typed = svc.recipient_count()

        first, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=typed)
        second, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=typed)

        assert first and not second
        assert len(popen_calls) == 1

    def test_spawns_the_job_in_its_own_session(self, admin_id, popen_calls, mailgun):
        broadcast_id = start_send(admin_id, mailgun)

        (cmd, kwargs), = popen_calls
        assert cmd[1].endswith(os.path.join("scripts", "send_broadcast_email.py"))
        assert cmd[2:] == ["--id", str(broadcast_id), "--base-url", BASE_URL]
        assert kwargs["start_new_session"] is True

    def test_the_script_runs_the_send_start_spawned(self, admin_id, popen_calls, mailgun, monkeypatch):
        start_send(admin_id, mailgun)
        (cmd, _), = popen_calls
        spec = importlib.util.spec_from_file_location("send_broadcast_email", cmd[1])
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        monkeypatch.setattr(sys, "argv", cmd[1:])

        assert script.main() == 0
        assert mailgun.recipients == ["sjef@example.com"]

    def test_a_failed_spawn_is_reported_and_can_be_retried(self, admin_id, mailgun, monkeypatch):
        def no_process(*args, **kwargs):
            raise OSError("no process")
        monkeypatch.setattr(svc.subprocess, "Popen", no_process)
        broadcast_id = tested_draft(admin_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert svc.get_status(broadcast_id)["state"] == "stopped"

    def test_refused_while_another_send_is_running(self, admin_id, popen_calls, mailgun, held_lock):
        broadcast_id = tested_draft(admin_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert popen_calls == []

    def test_refused_while_another_send_is_just_starting(self, admin_id, popen_calls, mailgun):
        start_send(admin_id, mailgun)
        second = tested_draft(admin_id)

        ok, _ = svc.start(second, admin_id, BASE_URL, typed_count=svc.recipient_count())

        assert not ok
        assert len(popen_calls) == 1

    def test_a_new_send_closes_an_earlier_stopped_one(self, db_session, admin_id, popen_calls, mailgun):
        add_user(db_session, "a", "a@example.com")
        mailgun.failing.add("a@example.com")
        earlier = start_send(admin_id, mailgun)
        run(earlier)
        assert svc.get_status(earlier)["state"] == "stopped"
        mailgun.failing.clear()

        start_send(admin_id, mailgun)

        assert svc.get_status(earlier)["state"] == "closed"
        assert row_states(db_session, earlier) == []


class TestRun:
    def test_sends_each_recipient_once_then_keeps_only_the_counts(
        self, db_session, admin_id, popen_calls, mailgun
    ):
        add_user(db_session, "a", "a@example.com")
        add_user(db_session, "b", "b@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        assert run(broadcast_id) == 0

        assert sorted(mailgun.recipients) == ["a@example.com", "b@example.com", "sjef@example.com"]
        status = svc.get_status(broadcast_id)
        assert status["state"] == "done"
        assert (status["total"], status["sent"], status["failed"], status["remaining"]) == (3, 3, 0, 0)
        assert row_states(db_session, broadcast_id) == []

    def test_refuses_a_send_that_was_never_started(self, admin_id, mailgun):
        broadcast_id = tested_draft(admin_id, mailgun=mailgun)

        assert run(broadcast_id) == 1

        assert mailgun.sent == []
        assert svc.get_status(broadcast_id)["state"] == "draft"

    def test_finished_send_cannot_be_run_again(self, admin_id, popen_calls, mailgun):
        broadcast_id = start_send(admin_id, mailgun)
        run(broadcast_id)
        mailgun.sent.clear()

        assert run(broadcast_id) == 1
        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL)

        assert not ok
        assert mailgun.sent == []

    def test_held_lock_exits_with_3_and_sends_nothing(self, admin_id, popen_calls, mailgun, job_env):
        broadcast_id = start_send(admin_id, mailgun)
        f = open(job_env / svc.LOCK_NAME, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert run(broadcast_id) == 3
        finally:
            f.close()

        assert mailgun.sent == []

    def test_resume_only_sends_to_those_who_failed(self, db_session, admin_id, popen_calls, mailgun):
        add_user(db_session, "a", "a@example.com")
        mailgun.failing.add("a@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        assert run(broadcast_id) == 1

        status = svc.get_status(broadcast_id)
        assert status["state"] == "stopped"
        assert (status["sent"], status["failed"]) == (1, 1)
        mailgun.failing.clear()
        mailgun.sent.clear()

        assert resume(broadcast_id, admin_id) == 0

        assert mailgun.recipients == ["a@example.com"]
        status = svc.get_status(broadcast_id)
        assert status["state"] == "done"
        assert (status["sent"], status["failed"]) == (2, 0)

    def test_killed_mid_send_is_shown_as_stopped_and_never_resends_the_one_in_flight(
        self, db_session, admin_id, popen_calls, mailgun
    ):
        add_user(db_session, "a", "a@example.com")
        add_user(db_session, "b", "b@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        def die_on_a(data):
            if data["to"] == "a@example.com":
                raise Killed()
        mailgun.on_send = die_on_a
        with pytest.raises(Killed):
            run(broadcast_id)
        mailgun.on_send = None
        age_start(db_session, broadcast_id)

        assert svc.get_status(broadcast_id)["state"] == "stopped"

        assert resume(broadcast_id, admin_id) == 0

        assert sorted(mailgun.recipients) == ["a@example.com", "b@example.com", "sjef@example.com"]
        status = svc.get_status(broadcast_id)
        assert status["state"] == "done"
        assert (status["sent"], status["unknown"]) == (2, 1)

    def test_stops_after_five_failures_in_a_row(self, db_session, admin_id, popen_calls, mailgun):
        for i in range(8):
            address = f"u{i}@example.com"
            add_user(db_session, f"u{i}", address)
            mailgun.failing.add(address)
        broadcast_id = start_send(admin_id, mailgun)

        assert run(broadcast_id) == 1

        # The admin's own address goes first and succeeds, then five fail.
        assert len(mailgun.sent) == 6
        status = svc.get_status(broadcast_id)
        assert status["state"] == "stopped"
        assert status["reason"]
        assert status["remaining"] == 3

    def test_scattered_failures_do_not_stop_the_send(self, db_session, admin_id, popen_calls, mailgun):
        for i in range(12):
            address = f"u{i}@example.com"
            add_user(db_session, f"u{i}", address)
            if i % 2 == 0:
                mailgun.failing.add(address)
        broadcast_id = start_send(admin_id, mailgun)

        run(broadcast_id)

        assert len(mailgun.sent) == 13
        assert svc.get_status(broadcast_id)["failed"] == 6

    def test_stop_request_halts_the_send_and_resume_finishes_it(
        self, db_session, admin_id, popen_calls, mailgun
    ):
        add_user(db_session, "a", "a@example.com")
        add_user(db_session, "b", "b@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        def stop_after_first(_data):
            svc.request_stop(broadcast_id)
            mailgun.on_send = None
        mailgun.on_send = stop_after_first
        assert run(broadcast_id) == 0

        assert len(mailgun.sent) == 1
        status = svc.get_status(broadcast_id)
        assert status["state"] == "stopped"
        assert status["remaining"] == 2

        assert resume(broadcast_id, admin_id) == 0

        assert len(mailgun.sent) == 3
        assert len(set(mailgun.recipients)) == 3
        assert svc.get_status(broadcast_id)["state"] == "done"

    def test_unsubscribing_during_the_send_is_honoured(self, db_session, admin_id, popen_calls, mailgun):
        second = add_user(db_session, "a", "a@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        def unsubscribe_second(_data):
            svc.set_opt_out(second, True)
        mailgun.on_send = unsubscribe_second
        run(broadcast_id)

        assert mailgun.recipients == ["sjef@example.com"]
        status = svc.get_status(broadcast_id)
        assert status["state"] == "done"
        assert status["skipped"] == 1

    def test_user_deleted_during_the_send_is_skipped(self, db_session, admin_id, popen_calls, mailgun):
        second = add_user(db_session, "a", "a@example.com")
        broadcast_id = start_send(admin_id, mailgun)
        db_session.query(DBUser).filter_by(id=second).delete()
        db_session.commit()

        run(broadcast_id)

        assert mailgun.recipients == ["sjef@example.com"]

    def test_unexpected_error_stops_the_send_with_a_reason(self, admin_id, popen_calls, mailgun, monkeypatch):
        broadcast_id = start_send(admin_id, mailgun)

        def broken(*args, **kwargs):
            raise RuntimeError("boom")
        monkeypatch.setattr(svc, "render_email", broken)

        assert run(broadcast_id) == 1

        status = svc.get_status(broadcast_id)
        assert status["state"] == "stopped"
        assert status["reason"]
        assert status["remaining"] == 1


class TestEmailSent:
    def test_each_email_links_to_unsubscribing_in_body_and_header(self, admin_id, popen_calls, mailgun):
        run(start_send(admin_id, mailgun))

        data = mailgun.sent[0]
        link = re.search(r"https://example\.test/minside/avmeld/\S+", data["text"]).group(0)
        assert link in data["html"]
        assert data["h:List-Unsubscribe"] == f"<{link}>"

    def test_replies_go_to_support(self, admin_id, popen_calls, mailgun):
        run(start_send(admin_id, mailgun))

        assert mailgun.sent[0]["h:Reply-To"] == "support@turnushjelper.no"

    def test_subject_and_body_are_the_admins_text(self, admin_id, popen_calls, mailgun):
        run(start_send(admin_id, mailgun, subject="Redusert stilling", body="Se Min tur"))

        data = mailgun.sent[0]
        assert data["subject"] == "Redusert stilling"
        assert "Se Min tur" in data["text"]
        assert "Se Min tur" in data["html"]

    def test_test_email_is_marked_in_the_subject(self, admin_id, mailgun):
        _, _, broadcast_id = svc.create_draft("Nyhet", "Tekst", admin_id)

        svc.send_test(broadcast_id, "sjef@example.com", admin_id, BASE_URL)

        assert mailgun.sent[0]["subject"] == "[TEST] Nyhet"


class TestRendering:
    def test_html_in_the_body_is_escaped_in_html_and_left_alone_in_text(self):
        text, html = svc.render_email("Emne", "<script>x</script> & <b>", "https://u.test/a")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp; &lt;b&gt;" in html
        assert "<script>x</script> & <b>" in text

    def test_blank_lines_become_paragraphs_and_single_newlines_breaks(self):
        _, html = svc.render_email("Emne", "En\nto\n\nTre", "https://u.test/a")

        assert "<p>En<br>to</p>" in html
        assert "<p>Tre</p>" in html

    def test_urls_become_links_without_trailing_punctuation(self):
        _, html = svc.render_email("Emne", "Se https://x.test/a?b=1&c=2. Takk", "https://u.test/a")

        assert '<a href="https://x.test/a?b=1&amp;c=2">https://x.test/a?b=1&amp;c=2</a>. Takk' in html

    def test_other_schemes_do_not_become_links(self):
        _, html = svc.render_email("Emne", "javascript:alert(1) ftp://x.test", "https://u.test/a")

        assert "javascript:alert(1) ftp://x.test" in html
        assert 'href="javascript' not in html
        assert 'href="ftp' not in html

    def test_the_unsubscribe_link_is_not_escaped_in_the_text_version(self):
        text, _ = svc.render_email("Emne", "Tekst", "https://u.test/a?x=1&y=2")

        assert "https://u.test/a?x=1&y=2" in text


class TestDraftText:
    @pytest.mark.parametrize("subject, body", [
        ("", "Tekst"),
        ("   ", "Tekst"),
        ("Emne", ""),
        ("Emne", " \n "),
        ("E" * 201, "Tekst"),
        ("Emne", "T" * 20001),
    ])
    def test_unusable_text_is_refused(self, admin_id, subject, body):
        ok, _, broadcast_id = svc.create_draft(subject, body, admin_id)

        assert not ok
        assert broadcast_id is None

    def test_newlines_in_the_subject_cannot_reach_the_email(self, db_session, admin_id):
        _, _, broadcast_id = svc.create_draft("Linje\r\nX-Header: y", "Tekst", admin_id)

        assert svc.get_broadcast(broadcast_id)["subject"] == "Linje X-Header: y"

    def test_browser_line_endings_are_normalised(self, admin_id):
        _, _, broadcast_id = svc.create_draft("Emne", "En\r\n\r\nTo", admin_id)

        assert svc.get_broadcast(broadcast_id)["body"] == "En\n\nTo"

    def test_test_email_needs_an_address(self, admin_id, mailgun):
        _, _, broadcast_id = svc.create_draft("Emne", "Tekst", admin_id)

        ok, _ = svc.send_test(broadcast_id, "adminbruker", admin_id, BASE_URL)

        assert not ok
        assert mailgun.sent == []


class TestAfterAStop:
    def _stopped(self, db_session, admin_id, mailgun, body="Feil tekst"):
        add_user(db_session, "a", "a@example.com")
        mailgun.failing.add("a@example.com")
        broadcast_id = start_send(admin_id, mailgun, body=body)
        run(broadcast_id)
        mailgun.failing.clear()
        mailgun.sent.clear()
        return broadcast_id

    def test_corrected_text_needs_a_new_test_and_reaches_only_those_remaining(
        self, db_session, admin_id, popen_calls, mailgun
    ):
        broadcast_id = self._stopped(db_session, admin_id, mailgun)

        ok, _ = svc.update_text(broadcast_id, "Nyhet", "Riktig tekst")
        assert ok

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL)
        assert not ok

        svc.send_test(broadcast_id, "sjef@example.com", admin_id, BASE_URL)
        mailgun.sent.clear()
        assert resume(broadcast_id, admin_id) == 0

        assert mailgun.recipients == ["a@example.com"]
        assert "Riktig tekst" in mailgun.sent[0]["text"]

    def test_close_gives_up_on_the_rest_and_keeps_the_counts(self, db_session, admin_id, popen_calls, mailgun):
        broadcast_id = self._stopped(db_session, admin_id, mailgun)

        ok, _ = svc.close(broadcast_id)

        assert ok
        status = svc.get_status(broadcast_id)
        assert status["state"] == "closed"
        assert (status["total"], status["sent"], status["failed"]) == (2, 1, 1)
        assert row_states(db_session, broadcast_id) == []

    def test_closed_send_cannot_be_resumed(self, db_session, admin_id, popen_calls, mailgun):
        broadcast_id = self._stopped(db_session, admin_id, mailgun)
        svc.close(broadcast_id)

        ok, _ = svc.start(broadcast_id, admin_id, BASE_URL)

        assert not ok

    @pytest.mark.parametrize("action", [
        lambda i: svc.update_text(i, "Ny", "Ny"),
        lambda i: svc.close(i),
    ])
    def test_a_running_send_cannot_be_edited_or_closed(self, admin_id, popen_calls, mailgun, held_lock, action):
        broadcast_id = tested_draft(admin_id, mailgun=mailgun)
        _force_sending(broadcast_id)

        ok, _ = action(broadcast_id)

        assert not ok
        assert svc.get_status(broadcast_id)["state"] == "sending"

    def test_a_draft_cannot_be_closed(self, admin_id):
        _, _, broadcast_id = svc.create_draft("Emne", "Tekst", admin_id)

        ok, _ = svc.close(broadcast_id)

        assert not ok

    def test_finished_send_cannot_be_edited(self, admin_id, popen_calls, mailgun):
        broadcast_id = start_send(admin_id, mailgun)
        run(broadcast_id)

        ok, _ = svc.update_text(broadcast_id, "Ny", "Ny")

        assert not ok


def _force_sending(broadcast_id):
    db_session = svc.get_db_session()
    try:
        db_session.get(BroadcastEmail, broadcast_id).state = "sending"
        db_session.get(BroadcastEmail, broadcast_id).started_at = datetime.now() - timedelta(minutes=5)
        db_session.commit()
    finally:
        db_session.close()


class TestLiveness:
    def test_just_started_counts_as_sending_before_the_job_has_the_lock(self, admin_id, popen_calls, mailgun):
        broadcast_id = start_send(admin_id, mailgun)

        assert svc.get_status(broadcast_id)["state"] == "sending"

    def test_lock_held_counts_as_sending_however_long_it_has_run(self, admin_id, mailgun, held_lock):
        broadcast_id = tested_draft(admin_id, mailgun=mailgun)
        _force_sending(broadcast_id)

        assert svc.get_status(broadcast_id)["state"] == "sending"

    def test_process_gone_counts_as_stopped_with_a_reason(self, admin_id, mailgun):
        broadcast_id = tested_draft(admin_id, mailgun=mailgun)
        _force_sending(broadcast_id)

        status = svc.get_status(broadcast_id)

        assert status["state"] == "stopped"
        assert status["reason"]


class TestToken:
    def test_token_round_trips_to_the_user(self):
        assert svc.user_id_from_token(svc.unsubscribe_token(42)) == 42

    @pytest.mark.parametrize("token", ["", "garbage", "1.abc"])
    def test_garbage_is_rejected(self, token):
        assert svc.user_id_from_token(token) is None

    def test_tampered_token_is_rejected(self):
        token = svc.unsubscribe_token(42)

        assert svc.user_id_from_token("9" + token[1:]) is None

    def test_token_signed_for_another_purpose_is_rejected(self):
        from itsdangerous import URLSafeSerializer

        other = URLSafeSerializer(svc.AppConfig.SECRET_KEY, salt="something-else").dumps(42)

        assert svc.user_id_from_token(other) is None


class TestOptOut:
    def test_applies_to_every_account_with_that_address(self, db_session, patch_db):
        first = add_user(db_session, "a", "Same@example.com")
        add_user(db_session, "b", "same@example.com")
        other = add_user(db_session, "c", "other@example.com")

        svc.set_opt_out(first, True)

        assert svc.recipient_count() == 1
        assert svc.is_opted_out(other) is False

    def test_can_be_turned_back_on(self, db_session, patch_db):
        user = add_user(db_session, "a", "a@example.com")

        svc.set_opt_out(user, True)
        assert svc.is_opted_out(user) is True

        svc.set_opt_out(user, False)
        assert svc.is_opted_out(user) is False
        assert svc.recipient_count() == 1

    def test_user_without_address_changes_only_itself(self, db_session, patch_db):
        first = add_user(db_session, "a", None)
        second = add_user(db_session, "b", None)

        svc.set_opt_out(first, True)

        assert svc.is_opted_out(first) is True
        assert svc.is_opted_out(second) is False

    def test_unknown_user_is_reported(self, db_session, patch_db):
        assert svc.set_opt_out(999999, True) is False


@pytest.fixture()
def admin_client(client, admin_user):
    login_user(client, admin_user["username"], admin_user["password"])
    return client


def create_via_page(admin_client, subject="Nyhet", body="Tekst"):
    response = admin_client.post("/admin/epost", data={"subject": subject, "body": body})
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[1])


def send_test_via_page(admin_client, broadcast_id, address="admin@example.com"):
    return admin_client.post(f"/admin/epost/{broadcast_id}/test", data={"address": address})



class TestAdminAccess:
    @pytest.mark.parametrize("method, path", [
        ("get", "/admin/epost"),
        ("post", "/admin/epost"),
        ("get", "/admin/epost/1"),
        ("post", "/admin/epost/1/rediger"),
        ("post", "/admin/epost/1/test"),
        ("post", "/admin/epost/1/send"),
        ("post", "/admin/epost/1/stopp"),
        ("post", "/admin/epost/1/avslutt"),
        ("get", "/admin/epost/1/status"),
    ])
    def test_regular_user_cannot_reach_it(self, client, sample_user, method, path):
        login_user(client, sample_user["username"], sample_user["password"])

        response = getattr(client, method)(path, headers={"X-Requested-With": "XMLHttpRequest"})

        assert response.status_code == 403

    def test_logged_out_visitor_is_sent_to_login(self, client):
        response = client.get("/admin/epost")

        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_regular_user_cannot_create_a_draft(self, client, sample_user, db_session):
        login_user(client, sample_user["username"], sample_user["password"])

        client.post("/admin/epost", data={"subject": "Nyhet", "body": "Tekst"})

        assert db_session.query(BroadcastEmail).count() == 0


class TestAdminPages:
    def test_dashboard_links_to_the_page(self, admin_client):
        assert b'href="/admin/epost"' in admin_client.get("/admin/dashboard").data

    def test_index_shows_the_recipient_count(self, admin_client, db_session):
        add_user(db_session, "a", "a@example.com")

        html = admin_client.get("/admin/epost").get_data(as_text=True)

        assert re.search(r'id="recipient-count"[^>]*>\s*2\b', html)

    @pytest.mark.parametrize("setting, expected", [
        ("", "slått av"),
        ("a@example.com", "a@example.com"),
        ("all", "alle"),
    ])
    def test_index_shows_the_servers_mode(self, admin_client, monkeypatch, setting, expected):
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", setting)

        html = admin_client.get("/admin/epost").get_data(as_text=True)

        assert expected in re.search(r'id="sending-mode".*?</div>', html, re.S).group(0)

    def test_creating_a_draft_opens_it_with_its_text(self, admin_client):
        response = admin_client.post(
            "/admin/epost", data={"subject": "Redusert stilling", "body": "Se Min tur"}, follow_redirects=True
        )

        html = response.get_data(as_text=True)
        assert "Redusert stilling" in html
        assert "Se Min tur" in html

    def test_refused_text_is_explained_on_the_page(self, admin_client, db_session):
        response = admin_client.post("/admin/epost", data={"subject": "", "body": "Tekst"}, follow_redirects=True)

        assert "Emne mangler" in response.get_data(as_text=True)
        assert db_session.query(BroadcastEmail).count() == 0

    def test_unknown_email_is_not_found(self, admin_client):
        assert admin_client.get("/admin/epost/999").status_code == 404
        assert admin_client.get("/admin/epost/999/status").status_code == 404

    def test_preview_is_sandboxed_and_cannot_run_the_text(self, admin_client):
        broadcast_id = create_via_page(admin_client, body="<script>alert(1)</script>")

        html = admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

        assert re.search(r"<iframe[^>]*\bsandbox\b[^>]*\bsrcdoc=", html)
        assert "<script>alert(1)" not in html

    def test_test_address_is_prefilled_with_the_admins_own(self, admin_client):
        broadcast_id = create_via_page(admin_client)

        html = admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

        assert re.search(r'name="address"[^>]*value="admin@example.com"', html)

    def test_test_address_is_blank_if_the_admin_has_no_real_address(self, client, db_session, patch_db):
        from app.services.user_service import hash_password

        add_user(db_session, "adminbruker", "adminbruker", is_auth=1, password=hash_password("passord123"))
        login_user(client, "adminbruker", "passord123")
        broadcast_id = create_via_page(client)

        html = client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

        assert re.search(r'name="address"[^>]*value=""', html)

    def test_send_form_is_absent_when_the_server_has_sending_off(self, admin_client, monkeypatch):
        monkeypatch.setattr(svc.AppConfig, "BROADCAST_RECIPIENTS", "")
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)

        html = admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

        assert f"/admin/epost/{broadcast_id}/send" not in html

    def test_send_form_appears_once_a_test_has_been_sent(self, admin_client):
        broadcast_id = create_via_page(admin_client)
        path = f"/admin/epost/{broadcast_id}/send"

        assert path not in admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

        send_test_via_page(admin_client, broadcast_id)

        assert path in admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True)

    def test_every_form_carries_a_csrf_token(self, admin_client, popen_calls, mailgun, db_session):
        """Tests run with CSRF off, so a form missing it would pass here and
        then fail for a real admin."""
        add_user(db_session, "a", "a@example.com")
        mailgun.failing.add("a@example.com")
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)
        pages = [
            admin_client.get("/admin/epost").get_data(as_text=True),
            admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True),
        ]
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "2"})
        run(broadcast_id)
        pages.append(admin_client.get(f"/admin/epost/{broadcast_id}").get_data(as_text=True))

        for html in pages:
            forms = re.findall(r'<form[^>]*method="POST".*?</form>', html, re.S)
            assert forms
            for form in forms:
                assert 'name="csrf_token"' in form


class TestAdminFlow:
    def test_write_test_send_and_follow(self, admin_client, popen_calls, mailgun):
        broadcast_id = create_via_page(admin_client)

        assert send_test_via_page(admin_client, broadcast_id).status_code == 302
        assert mailgun.recipients == ["admin@example.com"]
        mailgun.sent.clear()

        response = admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})
        assert response.status_code == 302

        (cmd, _), = popen_calls
        assert cmd[2:] == ["--id", str(broadcast_id), "--base-url", "http://localhost/"]
        assert admin_client.get(f"/admin/epost/{broadcast_id}/status").get_json()["state"] == "sending"

        svc.run(broadcast_id, cmd[5], log=lambda _: None)

        assert mailgun.recipients == ["admin@example.com"]
        status = admin_client.get(f"/admin/epost/{broadcast_id}/status").get_json()
        assert (status["state"], status["sent"]) == ("done", 1)

    def test_the_history_says_who_sent_it_and_how_it_went(self, admin_client, popen_calls, mailgun):
        broadcast_id = create_via_page(admin_client, subject="Redusert stilling")
        send_test_via_page(admin_client, broadcast_id)
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})
        run(broadcast_id)

        html = admin_client.get("/admin/epost").get_data(as_text=True)

        row = re.search(r"<tr[^>]*>(?:(?!</tr>).)*Redusert stilling.*?</tr>", html, re.S).group(0)
        assert "adminuser" in row
        assert re.search(r">\s*1 av 1\s*<", row)

    def test_sending_without_a_test_is_refused_and_explained(self, admin_client, popen_calls):
        broadcast_id = create_via_page(admin_client)

        response = admin_client.post(
            f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"}, follow_redirects=True
        )

        assert "Send en test først" in response.get_data(as_text=True)
        assert popen_calls == []

    @pytest.mark.parametrize("typed", ["", "abc", "99"])
    def test_wrong_typed_count_is_refused(self, admin_client, popen_calls, typed):
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)

        response = admin_client.post(
            f"/admin/epost/{broadcast_id}/send", data={"confirm_count": typed}, follow_redirects=True
        )

        assert "Antallet stemmer ikke" in response.get_data(as_text=True)
        assert popen_calls == []

    def test_double_submit_starts_one_job(self, admin_client, popen_calls):
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)

        for _ in range(2):
            admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})

        assert len(popen_calls) == 1

    def test_editing_saves_the_text_and_requires_a_new_test(self, admin_client, popen_calls):
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)

        admin_client.post(f"/admin/epost/{broadcast_id}/rediger", data={"subject": "Nytt emne", "body": "Ny tekst"})

        assert svc.get_broadcast(broadcast_id)["subject"] == "Nytt emne"
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})
        assert popen_calls == []

    def test_stop_asks_the_running_send_to_stop(self, admin_client, popen_calls):
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})

        admin_client.post(f"/admin/epost/{broadcast_id}/stopp")

        assert svc.get_status(broadcast_id)["stop_requested"] is True

    def test_a_stopped_send_can_be_continued_without_retyping_the_count(
        self, admin_client, popen_calls, mailgun
    ):
        mailgun.failing.add("admin@example.com")
        broadcast_id = create_via_page(admin_client)
        mailgun.failing.clear()
        send_test_via_page(admin_client, broadcast_id)
        mailgun.failing.add("admin@example.com")
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})
        run(broadcast_id)
        assert svc.get_status(broadcast_id)["state"] == "stopped"
        mailgun.failing.clear()

        admin_client.post(f"/admin/epost/{broadcast_id}/send")

        assert len(popen_calls) == 2

    def test_closing_a_stopped_send(self, admin_client, popen_calls, mailgun):
        broadcast_id = create_via_page(admin_client)
        send_test_via_page(admin_client, broadcast_id)
        mailgun.failing.add("admin@example.com")
        admin_client.post(f"/admin/epost/{broadcast_id}/send", data={"confirm_count": "1"})
        run(broadcast_id)

        admin_client.post(f"/admin/epost/{broadcast_id}/avslutt")

        assert svc.get_status(broadcast_id)["state"] == "closed"


class TestUnsubscribePage:
    def _path(self, user_id):
        return "/minside/avmeld/" + svc.unsubscribe_token(user_id)

    def test_built_link_reaches_the_page(self, client, db_session, patch_db):
        user = add_user(db_session, "a", "a@example.com")

        url = svc.unsubscribe_url("http://localhost/", user)

        assert url.startswith("http://localhost/minside/avmeld/")
        assert client.get(url[len("http://localhost"):]).status_code == 200

    def test_opening_the_link_changes_nothing(self, client, db_session, patch_db):
        user = add_user(db_session, "a", "a@example.com")

        client.get(self._path(user))

        assert svc.is_opted_out(user) is False

    def test_confirming_works_without_logging_in(self, client, db_session, patch_db):
        user = add_user(db_session, "a", "a@example.com")

        response = client.post(self._path(user), follow_redirects=True)

        assert response.status_code == 200
        assert svc.is_opted_out(user) is True
        assert "meldt av" in response.get_data(as_text=True)

    def test_confirm_form_works_with_csrf_on(self, app, client, db_session, patch_db):
        user = add_user(db_session, "a", "a@example.com")
        app.config["WTF_CSRF_ENABLED"] = True
        html = client.get(self._path(user)).get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

        response = client.post(self._path(user), data={"csrf_token": token})

        assert response.status_code == 302
        assert svc.is_opted_out(user) is True

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_bad_token_is_explained_and_changes_nothing(self, client, db_session, patch_db, method):
        user = add_user(db_session, "a", "a@example.com")

        response = getattr(client, method)("/minside/avmeld/garbage")

        assert response.status_code == 400
        assert "Min side" in response.get_data(as_text=True)
        assert svc.is_opted_out(user) is False

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_token_of_a_deleted_user_is_explained(self, client, patch_db, method):
        assert getattr(client, method)(self._path(999999)).status_code == 400

    def test_link_from_a_real_email_stops_the_next_one_for_that_user_only(
        self, client, db_session, admin_id, popen_calls, mailgun
    ):
        add_user(db_session, "a", "a@example.com")
        run(start_send(admin_id, mailgun))
        data = next(d for d in mailgun.sent if d["to"] == "a@example.com")
        link = re.search(r"https://example\.test(/minside/avmeld/\S+)", data["text"]).group(1)
        mailgun.sent.clear()

        client.post(link)
        run(start_send(admin_id, mailgun))

        assert mailgun.recipients == ["sjef@example.com"]


class TestMinSide:
    def test_setting_starts_on(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])

        html = client.get("/minside/").get_data(as_text=True)

        assert re.search(r'<input[^>]*name="announcements"[^>]*\bchecked\b', html)

    def test_turning_it_off_and_on(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])

        client.post("/minside/kunngjoringer", data={})
        assert svc.is_opted_out(sample_user["id"]) is True
        html = client.get("/minside/").get_data(as_text=True)
        assert not re.search(r'<input[^>]*name="announcements"[^>]*\bchecked\b', html)

        client.post("/minside/kunngjoringer", data={"announcements": "on"})
        assert svc.is_opted_out(sample_user["id"]) is False

    def test_form_carries_a_csrf_token(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])

        html = client.get("/minside/").get_data(as_text=True)

        form = re.search(r'<form[^>]*action="/minside/kunngjoringer".*?</form>', html, re.S).group(0)
        assert 'name="csrf_token"' in form

    def test_requires_login(self, client, db_session, patch_db):
        response = client.post("/minside/kunngjoringer", data={})

        assert response.status_code == 302
        assert "login" in response.headers["Location"]


class TestAccountCleanup:
    def test_deleting_a_user_removes_their_place_in_a_send(self, db_session, admin_id, popen_calls, mailgun):
        from app.services.user_service import delete_user

        user = add_user(db_session, "a", "a@example.com")
        broadcast_id = start_send(admin_id, mailgun)

        ok, _ = delete_user(user)

        assert ok
        remaining = db_session.execute(
            select(BroadcastRecipient.user_id).where(BroadcastRecipient.broadcast_id == broadcast_id)
        ).scalars().all()
        assert remaining == [admin_id]

    def test_deleting_an_admin_keeps_the_history_without_their_name(
        self, db_session, admin_id, popen_calls, mailgun
    ):
        from app.services.user_service import delete_user

        broadcast_id = start_send(admin_id, mailgun)
        run(broadcast_id)

        delete_user(admin_id)

        db_session.expire_all()
        row = db_session.get(BroadcastEmail, broadcast_id)
        assert row.created_by_id is None
        assert row.sent_by_id is None
        assert svc.get_status(broadcast_id)["sent"] == 1

    def test_resetting_an_account_to_a_stub_clears_the_opt_out(self, db_session, patch_db):
        from app.services import stub_service

        user = add_user(db_session, "a", "a@example.com", rullenummer="123", announcements_opt_out=1)

        ok, message = stub_service.reset_user_to_stub(user)

        assert ok, message
        assert svc.is_opted_out(user) is False
