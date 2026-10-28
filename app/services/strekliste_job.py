"""Generate a turnus set's strekliste in its own process.

Rendering the images, scanning double shifts and parsing the duties takes
minutes on the servers. Run inside the admin request, gunicorn's worker
timeout killed it partway (sync workers, --timeout 300). The admin button now
starts scripts/generate_strekliste.py, which calls run(), and the page polls
a status file next to the PDF. A file, because the poll may land on either
gunicorn worker.

An flock on a lock file marks a run in progress. The OS releases it when the
process ends, however it ends, so a killed run never leaves the button stuck.
"""

import fcntl
import json
import logging
import os
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime

from app.services import strekliste_service
from app.utils.pdf import strekliste_generator
from app.utils.pdf.double_shift_scanner import scan_double_shifts
from config import AppConfig

logger = logging.getLogger(__name__)

STATUS_NAME = ".generering.json"
LOCK_NAME = ".generering.lock"
LOG_NAME = "strekliste_generering.log"

# A started run has written no pid until its process has imported the app and
# taken the lock, which takes a few seconds.
START_GRACE_SECONDS = 60
# How long run() waits for the lock, so a status poll that probes it at the
# same instant cannot make a starting run give up.
LOCK_WAIT_SECONDS = 5

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "generate_strekliste.py",
)


def _dir(version):
    return os.path.join(AppConfig.turnusfiler_dir, version.lower(), "streklister")


def _write_status(version, status):
    os.makedirs(_dir(version), exist_ok=True)
    path = os.path.join(_dir(version), STATUS_NAME)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)
    os.replace(tmp, path)


@contextmanager
def _lock(version, wait_seconds=0.0):
    """Yield True while holding the run lock, False if another process has it."""
    os.makedirs(_dir(version), exist_ok=True)
    with open(os.path.join(_dir(version), LOCK_NAME), "w") as f:
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


def is_running(version):
    with _lock(version) as acquired:
        return not acquired


def read_status(version):
    """The latest run's status, or None if the set has never been generated
    this way. A run whose process is gone is reported as failed."""
    try:
        with open(os.path.join(_dir(version), STATUS_NAME), encoding="utf-8") as f:
            status = json.load(f)
    except (OSError, ValueError):
        return None
    if status.get("state") != "running" or is_running(version):
        return status
    starting = status.get("pid") is None and (
        time.time() - status.get("started_ts", 0) < START_GRACE_SECONDS
    )
    if starting:
        return status
    return {
        **status,
        "state": "failed",
        "error": f"Genereringen stoppet før den ble ferdig. Se app/logs/{LOG_NAME}.",
    }


def start(year_identifier, force):
    """Start a generation in the background. False if one is already running."""
    version = year_identifier.lower()
    if is_running(version):
        return False
    now = time.time()
    _write_status(version, {
        "state": "running", "step": "starter", "pid": None, "force": force,
        "started": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "started_ts": now,
    })
    cmd = [sys.executable, SCRIPT, "--year", year_identifier]
    if not force:
        cmd.append("--keep-images")
    os.makedirs(AppConfig.log_dir, exist_ok=True)
    with open(os.path.join(AppConfig.log_dir, LOG_NAME), "a") as log_file:
        # Its own session, so the process outlives the request and is not tied
        # to the gunicorn worker. A service restart still stops it; the image
        # swap and the single-transaction parse leave the old data intact then.
        subprocess.Popen(
            cmd,
            cwd=os.path.dirname(os.path.dirname(SCRIPT)),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return True


def run(year_identifier, force=True, log=print):
    """Render images, scan double shifts and parse the duties.

    Returns 0 when done, 1 when it failed, 3 when another run holds the lock.
    """
    from app.services.turnus_service import get_turnus_set_by_year

    year = year_identifier.upper()
    version = year.lower()
    with _lock(version, wait_seconds=LOCK_WAIT_SECONDS) as acquired:
        if not acquired:
            log(f"En generering for {year} kjører allerede.")
            return 3

        status = {
            "state": "running", "step": "bilder", "pid": os.getpid(), "force": force,
            "started": datetime.now().isoformat(timespec="seconds"),
            "started_ts": time.time(),
        }
        _write_status(version, status)
        try:
            result = _run_steps(year, version, force, status, log, get_turnus_set_by_year)
            status.update(state="done", step="ferdig", result=result)
            return 0
        except Exception as e:
            logger.exception("Strekliste generation failed for %s", year)
            log(traceback.format_exc())
            status.update(state="failed", error=str(e))
            return 1
        finally:
            status["finished"] = datetime.now().isoformat(timespec="seconds")
            _write_status(version, status)


def _run_steps(year, version, force, status, log, get_turnus_set_by_year):
    ts = get_turnus_set_by_year(year)
    if not ts:
        raise RuntimeError(f"Fant ikke turnussett {year}")
    paths = strekliste_generator.get_paths(version)
    if not paths["pdf_exists"]:
        raise RuntimeError(f"Fant ingen strekliste-PDF: {paths['pdf_path']}")
    log(f"Turnussett {year} (id {ts['id']}), PDF {paths['pdf_path']}")

    t = time.time()
    images = strekliste_generator.generate_all_images(version, force=force)
    if not images["success"]:
        raise RuntimeError(f"Bildegenerering feilet: {images.get('error')}")
    errors = images.get("errors", [])
    log(f"Bilder: {len(images['generated'])} generert, {len(images['skipped'])} hoppet over, "
        f"{len(errors)} feil av {images['total']} ({time.time() - t:.0f} s)")
    for err in errors[:10]:
        log(f"  feil: {err}")
    result = {
        "stasjoneringssted": paths.get("stasjoneringssted"),
        "generated": len(images["generated"]),
        "skipped": len(images["skipped"]),
        "errors": len(errors),
        "error_details": errors[:10],
        "total": images["total"],
    }

    # The scan and the parse each report their own failure rather than
    # failing the run: the images are already in place.
    status["step"] = "dobbeltskift"
    _write_status(version, status)
    t = time.time()
    try:
        double_shifts = scan_double_shifts(paths["pdf_path"])
        out = os.path.join(AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(double_shifts, f, indent=2, ensure_ascii=False)
            f.write("\n")
        result["double_shift_count"] = len(double_shifts.get("dobbelt_tur", []))
        result["delt_shift_count"] = len(double_shifts.get("delt_dagsverk", []))
        log(f"Dobbeltskift: {result['double_shift_count']} dobbelt tur, "
            f"{result['delt_shift_count']} delt dagsverk -> {out} ({time.time() - t:.0f} s)")
    except Exception as e:
        logger.exception("Double-shift scan failed for %s", year)
        result["double_shift_error"] = str(e)
        log(f"Dobbeltskift feilet: {e}")

    status["step"] = "strekliste"
    _write_status(version, status)
    t = time.time()
    try:
        rapport = strekliste_service.import_strekliste(ts["id"], paths["pdf_path"])
        result.update(
            strekliste_dagsverk=rapport["dagsverk"],
            strekliste_aktiviteter=rapport["aktiviteter"],
            strekliste_advarsler=rapport["advarsler"],
            strekliste_sidevarsler=rapport.get("sidevarsler", [])[:10],
        )
        log(f"Strekliste: {rapport['dagsverk']} dagsverk, {rapport['aktiviteter']} aktiviteter, "
            f"{rapport['advarsler']} med advarsler, per sted {rapport.get('per_sted')} "
            f"({time.time() - t:.0f} s)")
        for warning in rapport.get("sidevarsler", [])[:10]:
            log(f"  side: {warning}")
    except Exception as e:
        logger.exception("Strekliste parse failed for %s", year)
        result["strekliste_error"] = str(e)
        log(f"Lesing av streklisten feilet: {e}")

    return result
