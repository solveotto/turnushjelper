# TODO — Findings from the 2026-07-18 forensic audit

Full-codebase audit done 2026-07-18 on `main` (b1a4a8a). Baseline:
`venv/bin/pytest -q` → **368 passed, 0 failed** (2:38). The July 12 review's
fixes were all verified landed (versioned view-cache keys, turnusnokkel 404,
rullenummer collision checks, check-endpoint boolean responses, 7.fører parser).

> **Status (2026-07-18 evening):** Tasks 1.1 and 1.2 are **DONE** (371 passed).
> 1.1: POST-scoped limits on login (10/min), forgot-password (5/h),
> resend-verification (5/h), reset-password (10/h); covered by
> `tests/test_auth_routes.py::TestLoginRateLimit`. Note: the limiter is
> disabled in tests via `limiter.enabled = False` *after* `create_app()`
> (see `tests/conftest.py`), NOT via `RATELIMIT_ENABLED=false` as this file
> originally suggested — with the config flag off, Flask-Limiter's init_app
> skips storage setup and can never be re-enabled for the 429 test.
> `config.py` gained `RATELIMIT_ENABLED` as a prod emergency kill-switch.
> 1.2: tokens stored as SHA-256 (`_hash_token` in
> `app/services/auth_service.py`), raw token only in the emailed URL;
> covered by `test_auth_service.py::test_token_stored_hashed_not_raw` +
> updated direct-insert tests. Deploy note: outstanding raw-stored tokens
> become invalid — users just request a new link (≤48h expiry anyway).

> **Status (2026-07-20): Phase 0 is DONE.** Task 0.1 (R26 innplassering
> re-import) and Task 0.2 (prod PII file move) both verified — see their
> sections below for the full trail, including a real bug found and fixed
> along the way (a stale, non-restarted server process was silently writing
> wrong data during the first re-import attempt). Task 0.3 (gunicorn config)
> still open.

This file covers what the audit found still open, split into:

- **Phase 0** — operations, no code. Highest value, do first.
- **Phase 1** — security fixes, ready to implement, no decision needed.
- **Phase 2** — needs a decision from Solve first; options listed per task.
- **Phase 3** — structural cleanups, opportunistic, one PR each.

## Ground rules — read before touching anything

1. Read `CLAUDE.md` first and follow it exactly (three-layer architecture,
   raw-SQLAlchemy session pattern, Norwegian UI text / English code).
2. `python` is **not** on PATH. Use `venv/bin/python` and `venv/bin/pytest`.
3. Baseline is **368 passed**. Run the suite before starting and after every
   task. Any new failure you introduce must be fixed before moving on.
4. Read every file you edit *before* editing it. Locate code by the quoted
   snippets, not line numbers — they drift.
5. Do **not** commit or push unless Solve asks.

---

## Phase 0 — Operations (no code, ~30 min total)

### DONE Task 0.1: Re-import innplassering R26 in PRODUCTION

The parser fix for 7.fører linjer (2026-07-18) only corrects the DB at import
time. Until the re-import runs, prod 7th-drivers have row-counter linjer
(1..10) and see the wrong mintur column and kompdag count.

**Action:** admin UI → import innplassering for R26, or
`scripts/import_innplassering.py --year R26` on the server.
**Verify:** `venv/bin/python scripts/check_7th_drivers.py --year R26` on the
server — exits 0 and prints "All linjenummer values are in 1-6" when correct;
exits 1 and flags rows with `<-- INVALID` if the row-counter bug is still
present (re-run the import). Re-run this same check after any future
innplassering import (R27, ...).

> **Status (2026-07-19): re-import DONE** (via admin UI — confirmed the safe
> path, see below). **Verification pending re-run** — see 2026-07-20 note.
>
> **2026-07-20 — bug found in both standalone scripts, now fixed.**
> `scripts/check_7th_drivers.py` (written 2026-07-19) and the pre-existing
> `scripts/import_innplassering.py` both had
> `os.environ.setdefault("DB_TYPE", "sqlite")` near the top, run before
> `config.py`'s `load_dotenv()`. Since `load_dotenv()` never overrides an
> already-set env var, this silently shadowed a real `DB_TYPE=mysql` from
> `.env` — any standalone script run on the server queried/wrote to an
> **empty local SQLite file**, not production MySQL, with no error until a
> query needed a table that (obviously) didn't exist there
> (`sqlite3.OperationalError: no such table: turnus_sets`). Confirmed the
> R26 re-import itself is unaffected — Solve ran it via the **admin UI**,
> which runs inside the live Flask app where config loads correctly with no
> script-level override. Both scripts fixed (the `setdefault` line removed;
> each now prints `DB_TYPE=...` on startup so a future wrong-DB run fails
> loudly instead of silently). Ran the fixed script on the server
> (`DB_TYPE=mysql` confirmed correct) and found a **second, real** bug: 4 of
> 10 R26 7.fører rows had `linjenummer` 7-10 instead of 1-6.
>
> **2026-07-20 — root cause of the real data bug: stale running process, not
> stale code.** Full systematic-debugging investigation (see conversation for
> detail): re-parsing the actual PDF's raw text (via pdfplumber) proved the
> real "L" column values for all 10 rows are ordinary 1-6 — no PDF/data
> anomaly. Comparing prod's stored values against the PDF's row-counter
> column (position 1..10) row-for-row showed an **exact match**: prod's
> `linjenummer` was the row-counter for literally all 10 rows, not just the
> 4 that happened to also exceed 6 — the check script's 1-6 range check
> missed the other 6 because a row-counter value can coincidentally also be
> ≤6. Confirmed on the server: the checked-out file already had the
> 2026-07-18 fix (`grep -c "L column"` → `4`; `git log` → `b1a4a8a`, current
> HEAD) — so the code on disk was correct. The gunicorn process serving the
> admin-UI import had simply **never been restarted** since before that fix
> landed; Python caches an imported module in memory per-process and does
> not reload it when the file on disk changes, so the running worker kept
> executing the old row-counter-based parser regardless of what was on disk.
> **Fix is operational, not code:** `sudo systemctl restart turnushjelper`,
> re-run the R26 import via the admin UI (full delete+reinsert, so no
> partial/stale-row risk), then re-verify.
>
> Also hardened `scripts/check_7th_drivers.py` itself: it now re-parses the
> PDF fresh and compares row-for-row against the DB (immune to the
> coincidental-range-match blind spot above) instead of only checking
> "is linjenummer in 1-6" — verified locally by deliberately corrupting the
> dev DB with row-counter values and confirming all 10 are now flagged as
> `MISMATCH` (the old range-only check would have missed 6 of them). Falls
> back to the weaker range check only if the PDF can't be found to re-parse.
>
> **VERIFIED — Task 0.1 genuinely DONE.** Restarted `turnushjelper` on the
> server, re-ran the R26 innplassering import via the admin UI, ran
> `check_7th_drivers.py --year R26` on the server: `DB_TYPE=mysql`, all 10
> rows now match the ground-truth "L" column values independently extracted
> from the raw PDF during root-cause investigation (27180→4, 31397→6,
> 31482→2, 34290→1, 36022→1, 64895→3, 92468→5, 92707→4, 93235→3, 93386→2 —
> all confirmed). Note: the server ran the pre-strengthening version of the
> check script (weak 1-6 range check, not the fresh-parse comparison) —
> correctness here was confirmed by manual cross-check against the raw PDF,
> not by the script alone. The strengthened script exists only in the local
> repo; **push it before the next re-import** (R27, etc.) so the stronger
> check is what actually runs next time.

### DONE Task 0.2: Move PII files on the prod server (git-history purge deferred)

The code-side fix (`instance/protected/` + `app/utils/protected_paths.py`) is
done.

> **Status (2026-07-19): DONE** — Solve committed + pushed the backlog
> (`99252d5` and 6 following commits, none of which had reached `origin`
> before), pulled on the prod server, and ran the `mv` migration from
> `docs/guides/PROTECTED_FILES.md` (`medlemsliste.xlsx`, `ansinitet.pdf`,
> `r26/innplassering_R26.pdf` → `instance/protected/`), then restarted the
> service. Verified: `medlemsliste.xlsx`/`ansinitet.pdf`-adding commits
> (`da67f59`, `cbc6ef6`, `7c68683`, `29d226e`) were already on `origin/main`
> from an earlier push — pushing now added no new exposure there, it only
> shipped the fix. One follow-up surfaced during verification: the admin
> employees page still *displayed* the old `app/static/turnusfiler/…` path
> for medlemsliste/ansinitet (cosmetic only — the actual read path was
> already correct) — fixed same day, see Phase 3 Task 8 step 5.

**Deferred — git-history purge (conditional, not urgent).**
`medlemsliste.xlsx` is still recoverable from git history — added/modified in
commits `da67f59`, `cbc6ef6`, `7c68683`, `29d226e`, and confirmed live on
`origin/main` (private GitHub repo, Solve's sole account). Since Solve is the
**only** account with repo access, the purge defends against no real threat
today and carries the highest irreversibility risk in this file. **Run
`git filter-repo` to purge it ONLY before the repo is ever pushed to a shared
remote, given a collaborator, or handed to a contractor — and do it first,
before sharing** (coordinate with any clones; the history rewrite invalidates
them).

### [DONE] Task 0.3: Decide which gunicorn config is canonical

Root `gunicorn.conf.py` (bind :8080, timeout 60) and `deploy/gunicorn.conf.py`
(unix socket, timeout 300) diverge. Check what the systemd unit actually
references, then delete the other or mark it dev-only in a comment.

---

## Phase 1 — Security hardening, ready to implement

### DONE Task 1.1: Rate-limit login and password-reset flows

**Priority: highest code fix in this file.**

**Problem.** Only three endpoints are limited (`/register` POST `10 per hour`,
the two `check-*` APIs `30 per hour`). The limiter has no global default
(`default_limits=[]` in `app/extensions.py`), so `/login`,
`/forgot-password`, `/resend-verification` and `/reset-password/<token>` are
unthrottled: credential brute-force, plus a cheap CPU-exhaustion vector
(every attempt burns a bcrypt verify on a 2-worker/8-thread box).
`forgot_password` has a per-*email* DB throttle but nothing per-IP.

**Fix.** In `app/routes/auth.py` and `app/routes/registration.py`, import
`limiter` from `app.extensions` and add POST-scoped limits, e.g.:

```python
@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
```

Suggested: login `10 per minute`, forgot-password `5 per hour`,
resend-verification `5 per hour`, reset-password POST `10 per hour`. GET must
stay unlimited (`methods=["POST"]` on every limit).

**Pitfalls.**
- `memory://` storage is per-worker, so effective prod limits are ~2× the
  configured value (known, accepted — see the rate-limiter memory note).
  Set values with that in mind.
- Check how tests exercise login (`tests/conftest.py::login_user` logs in
  repeatedly across tests). Limiter state persists per test process — either
  the test app must disable the limiter (`RATELIMIT_ENABLED = False` in test
  config, mirroring how CSRF is disabled) or limits must be high enough not
  to trip the suite. Prefer explicit disable in tests + one dedicated test
  asserting a 429 (see `docs/guides/HIGH_TRAFFIC_MODE.md` staging steps for
  how the limiter was verified before).

**Verify.** Full suite + a new test: POST /login 11 times → 429.

### DONE Task 1.2: Store verification/reset tokens hashed

**Problem.** `EmailVerificationToken.token` stores the raw
`secrets.token_urlsafe(32)`. A DB/backup leak turns every outstanding
password-reset token into account takeover.

**Fix.** Hash at write, hash at lookup — no schema change needed
(sha256 hex is 64 chars, column is `String(255)`):

1. In `app/services/auth_service.py` add
   `_hash_token = lambda t: hashlib.sha256(t.encode()).hexdigest()` (as a
   proper function) and apply it in `create_verification_token`,
   `create_password_reset_token` (store hashed) and `verify_token`,
   `verify_password_reset_token` (hash the incoming token before the
   `filter_by(token=...)`).
2. The raw token still goes in the email link — only storage changes
   (`app/routes/auth.py` / `app/routes/registration.py` need no changes).
3. Outstanding unhashed tokens in prod become invalid on deploy — acceptable:
   they expire in ≤48h anyway; users just request a new link. Note it in the
   deploy message.

**Verify.** `tests/test_auth_service.py`, `tests/test_registration_routes.py`,
`tests/test_auth_routes.py`; add a test that the stored token differs from
the emailed one and that verification still succeeds end-to-end.

### DONE Task 1.3: Flip the `run.py` debug default to off

`run.py` enables the Werkzeug debugger unless `FLASK_DEBUG` is explicitly
false. If ever run directly on a server, that is remote code execution.

**Fix.** Default to `"false"` in the `os.environ.get`, and set
`FLASK_DEBUG=true` in `.env.example` (with a comment) so dev keeps the
current behavior after copying the example. Update the CLAUDE.md line
"debug on by default" to match.

### DONE Task 1.4: Delete the stale CSRF claim in docs/FORBEDRINGER.md

The file claims 18 admin routes lack CSRF validation. False since
`CSRFProtect` went global (`csrf.init_app` in `app/__init__.py`, meta token
in `base.html`, `X-CSRFToken` in `apiFetch`). A contributor acting on it
could break working code. Remove that bullet; keep or migrate the
NLF-nummer bullet somewhere it will be seen.

---

## Phase 2 — Needs a decision from Solve first. Present options, do not implement.

### DONE Task 2.1: Per-process shared state vs 2 gunicorn workers

> **Decision (2026-07-20): Option B.** Solve chose to document the envelope
> rather than add Redis. Redis buys automatic correctness for an event that
> happens a few times a year and charges a permanent new dependency on the
> single Hetzner box — and a Redis outage would take down caching *and* rate
> limiting, which is worse than the status quo's worst case (1 h of stale
> turnus data after an import you performed yourself).
>
> Two findings refined the original framing:
> - The **favorites race is already handled at the DB level** —
>   `UniqueConstraint('user_id', 'shift_title', 'turnus_set_id')`
>   (`app/models.py`) prevents duplicate favorites across workers. The
>   `favorite_lock` only orders `order_index` assignment; a cross-worker
>   collision is cosmetic and self-corrects on the next reorder. The lock was
>   kept and documented, not deleted.
> - **A service restart clears every worker at once**, closing the staleness
>   window to zero for the only case that matters. This was already informal
>   practice (see Task 0.1) and is now an explicit runbook step.
>
> Implemented: per-worker caveats on `invalidate_turnus_cache()` /
> `get_turnus_cache_generation()` (`app/utils/df_utils.py`, replacing the
> misleading "at once" wording), rationale comments on `cache` and
> `favorite_lock` (`app/extensions.py`), and a "Restart the service after any
> import" section + checklist item in
> `docs/guides/CREATING_TURNUS_SETS.md`. No behavior change; 371 passed.
>
> **Revisit Option A (Redis) when any of these becomes true:**
> 1. gunicorn workers scale past 2 (see `docs/guides/HIGH_TRAFFIC_MODE.md`,
>    which suggests 4 on a CX32) — the restart trick still works but the
>    stale-worker window widens;
> 2. cache invalidation becomes user-triggered rather than admin-rare;
> 3. a second app server is added (restart no longer covers the fleet).

Production runs `workers = 2`, but three mechanisms assume one process:

- **SimpleCache invalidation:** `invalidate_turnus_cache()` and the
  generation counter (`app/utils/df_utils.py`) only affect the worker that
  handled the admin request. The other worker serves stale turnus data up to
  1h (`CACHE_DEFAULT_TIMEOUT: 3600`), stale rendered pages 120–300s, stale
  kompdager up to 1h after a re-import. Same for
  `df_manager.reload_active_set()` in `refresh_turnus_set`.
- **`favorite_lock`** (`threading.Lock`) doesn't serialize reorders across
  workers.
- **Rate limiter `memory://`** — limits ~2× documented (known).

Options:

- **A (infra):** add Redis — `CACHE_TYPE: RedisCache` + limiter
  `storage_uri=redis://…`; delete `favorite_lock` and rely on DB-level
  ordering. Every existing invalidation call site becomes correct fleet-wide
  with no logic changes. Cost: a new service to run/monitor on the Hetzner
  box.
- **B (document):** accept the ≤1h staleness envelope after admin imports
  (they are rare), fix the misleading "all at once" comments in
  `df_utils.py`, and note the envelope in `docs/guides/CREATING_TURNUS_SETS.md`.
  Zero infra. The favorites race stays theoretical (same user, two tabs,
  two workers, same second).

### DONE (code) Task 2.2: DB unique constraint on `users.rullenummer`

> **Status (2026-07-20): implemented locally, NOT yet applied to prod.**
>
> Prod audit ran clean via the new `scripts/check_rullenummer_duplicates.py`
> (`DB_TYPE=mysql`, 395 users, 320 with a rullenummer, 0 duplicates, 0 empty
> strings) → migration written but **not deployed**. Remaining step is
> `venv/bin/alembic upgrade head` on the server.
>
> - `migrations/versions/017_unique_rullenummer.py` — note it **replaces**
>   the existing non-unique `ix_users_rullenummer` from migration 015 rather
>   than adding a second index. Up/down roundtrip verified on dev.
> - `app/models.py` — `rullenummer` gains `unique=True, index=True`
>   (mirroring `medlemsnummer`); model and DB had already drifted since 015
>   added its index out-of-band.
> - Tests: `test_models.py::TestDBUser::test_unique_rullenummer` and
>   `test_multiple_null_rullenummer_allowed` (NULL stays exempt — 75 prod
>   users depend on that).
>
> **Real bug the constraint exposed — `sync_members_from_excel` would have
> broken in production.** `absorb_twins()` and `absorb_fuzzy_twins()`
> (`app/services/user_service.py`) copied `rullenummer` from a duplicate stub
> onto the kept user and only *then* called `delete_stub()`, whose query
> autoflushes — so both rows briefly held the same value and the flush
> violated the index. Nulling the donor in memory first is **not** enough: a
> flush orders same-table UPDATEs by primary key, not assignment order, so
> the target's UPDATE can still land while the donor row exists. Both
> functions now capture the values, delete the stub (which flushes), then
> write to the target. 3 member-import tests caught this; all pass now.
> The same hazard already existed for `medlemsnummer` — hence the
> pre-existing flush comment inside `delete_stub()`.
>
> **Deploy order matters:** push this code *before* running the migration.
> The old absorb logic against a unique index breaks Excel member import.

App-level collision checks exist (`activate_stub_user`,
`create_user_with_email`, `update_user`), but any future write path that
forgets the check reintroduces cross-user innplassering exposure (the join
is on the rullenummer string). Blocked on a prod data audit:

1. Run on prod: `SELECT rullenummer, COUNT(*) FROM users WHERE rullenummer
   IS NOT NULL GROUP BY rullenummer HAVING COUNT(*) > 1;`
2. If clean → Alembic migration adding a unique index (partial/NULL-safe:
   MySQL allows multiple NULLs in a unique index, so plain unique works).
3. If duplicates → Solve adjudicates which user keeps the number first.

### Task 2.3: Session serialization: pickle → JSON

`app/utils/sa_session_interface.py` pickles session dicts into
`flask_sessions.data`. Only exploitable after DB compromise, but JSON removes
a deserialization gadget surface. Decision needed because deploying it logs
out everyone (existing pickled rows fail to parse → new session), unless a
read-pickle/write-JSON transition period is implemented. Options:
**A** hard cut (one-time global logout, trivial code), **B** dual-read for
30 days then remove pickle, **C** status quo. Recommend A at a quiet time.

---

## Phase 3 — Structural cleanups (opportunistic, one PR each)

1. **Session-interface test coupling:** `SqlAlchemySessionInterface` calls
   `SessionLocal` directly, bypassing `patch_db` — a fresh clone fails ~30
   login tests until a dev `dummy.db` with `flask_sessions` exists. Fix by
   monkeypatching `app.utils.sa_session_interface.SessionLocal` in
   `tests/conftest.py` (patch-at-use-site) so the suite passes from a clean
   checkout. Then delete the dummy.db workaround note in docs/memory.
2. **Split `app/services/user_service.py` (1,652 lines):** extract
   `member_sync_service.py` (`sync_members_from_excel`,
   `normalize_medlemsnummer`, `_normalize_name`) and `stub_service.py`
   (create/activate/delete/reset stub functions). Keep `db_utils` re-exports
   working during the move.
3. **Retire the `db_utils` facade route-by-route:** routes import services
   directly instead of the compat shim. Do it per-blueprint; the facade's
   from-import pattern already caused one real test bug (see comment in
   `api.py::mark_tour_seen`).
4. **Extract soknadsskjema document builders:** `_build_soknadsskjema_doc` /
   `_build_soknadsskjema_pdf` (~500 lines) out of
   `app/routes/shifts/soknadsskjema.py` into `app/utils/` — routes should
   hold no document-generation logic.
5. **Move `app/utils/tests/`** (test_ruler.py + PNG) under `tests/` — test
   artifacts shouldn't ship inside the app package.
6. **`datetime.utcnow()` → `datetime.now(timezone.utc)`** — deprecation
   warnings in the suite point at `app/routes/auth.py` (`login_at`); grep for
   the rest. Watch naive-vs-aware comparisons against DB-stored naive UTC
   (`auth_service.py` deliberately strips tzinfo — follow that convention).
7. **Escape interpolated shift data in JS:** `buildScheduleTableHTML` in
   `app/static/js/modules/oversikt.js` inserts `dg`/`tid` unescaped. Data is
   admin-imported (low risk), but add a small `escapeHtml` helper in
   `modules/utils.js` and use it here and in the other `innerHTML` template
   literals that carry data values.

8. **Move turnusfiler out of the public static tree** *(decided 2026-07-18:
   do it — biggest Phase 3 item. Corrected 2026-07-19 after a `.gitignore`
   review; run as its own session, not on a tight budget.)*

   **Problem.** `app/static/turnusfiler/` is the app's data store living in
   the unauthenticated public tree. Almost nothing there needs static
   serving: the JSONs/Excels/XLS are read server-side only, strekliste PNGs
   are served via the login-protected `/api/shift-image`, the turnus PDF via
   login-protected `/download_pdf`. The only direct static consumer is the
   PDF-downloads dropdown (`url_for("static", ...)` in
   `app/__init__.py` ~line 129). Meanwhile rotation schedules, the
   employer's raw `R26 endelig.xls`, nøkkel Excels and all generated PNGs
   are world-readable without login. "Tracked in git" (wanted — revision
   diffs and calibration tests use committed data) is only coupled to
   "publicly served" because the data sits under `app/static/`.

   **Two `.gitignore` traps (found 2026-07-19).** Current rules ignore
   `app/static/turnusfiler/**/*.pdf`, `**/*.png` and `**/double_shifts_*.json`
   — so PNGs and source PDFs under turnusfiler are **untracked** (schedule/
   stats JSONs and the `.xls`/nøkkel files are tracked; double_shifts JSONs
   are force-tracked despite the rule). Therefore:
   - **`git mv` on the directory would leave the untracked PNGs/PDFs behind.**
     Use a filesystem `mv` + `git add -A` instead.
   - **The ignore rules are pinned to the old path.** After the move they stop
     matching and generated PDFs/PNGs under `turnusdata/` become accidentally
     committable — `.gitignore` MUST be rewritten to the new root.

   **Target layout.**

   ```
   turnusdata/{r25,r26,...}/   ← tracked in git, NOT under app/, never served directly
   instance/protected/         ← untracked, PII only (unchanged)
   app/static/                 ← css/js/img only
   ```

   **Steps.**

   1. Move with the filesystem, not `git mv` (see trap above):
      ```
      mv app/static/turnusfiler turnusdata
      git add -A       # tracked JSON/Excel moves recorded as renames
      ```
      Untracked PNGs/PDFs follow on disk and stay untracked.
   2. Rewrite `.gitignore`: change the three `app/static/turnusfiler/**` rules
      to `turnusdata/**/*.pdf`, `turnusdata/**/*.png`,
      `turnusdata/**/double_shifts_*.json`. **Keep** the two
      `app/static/**/medlemsliste*.xlsx` / `app/static/**/ansinitet*.pdf`
      PII-block rules as defense-in-depth.
   3. Point `AppConfig.turnusfiler_dir` at the new root
      (`os.path.join(base_dir, "turnusdata")`); delete no other config. Then
      normalize the stragglers that build the path manually from
      `AppConfig.static_dir` + `"turnusfiler"` to use
      `AppConfig.turnusfiler_dir` instead — as of 2026-07-19:
      `app/utils/shift_stats.py` (3 sites), `app/utils/pdf/shiftscraper.py`,
      `app/utils/shift_matcher.py`,
      `app/services/import_turnusset_service.py`,
      `app/routes/admin/turnus.py`. Re-grep before trusting this list:
      `grep -rn 'static_dir.*turnusfiler\|"turnusfiler"' app/ tests/ scripts/`.
   4. Replace the static URL in the PDF-downloads context processor
      (`app/__init__.py`) with a new authed route, e.g.
      `/download/pdf/<filename>` in `app/routes/downloads.py`:
      `@login_required`, resolve the year dir from the user's turnus set,
      sanitize with `os.path.basename`, serve with `send_from_directory`
      (mirror the pattern in `api.py::get_shift_image`).
   5. ~~Fix the stale PII-path text in `app/templates/admin_employees.html`~~
      **DONE 2026-07-19** — lines 69/147 now show `instance/protected/…`
      instead of the old `app/static/turnusfiler/…` (display text only; the
      actual read path via `app/utils/protected_paths.py` was already
      correct, so no functional bug — just a misleading admin-page label).
   6. Update path references in tests (`test_data_integrity.py`,
      `test_import_turnusset_routes.py`, `test_kompdag_routes.py`,
      `test_protected_files.py`, `test_shift_stats.py`,
      `test_timeskjema_parser.py`, `tests/fixtures/README.md`) — most
      should go through `AppConfig.turnusfiler_dir` so this shrinks to
      near-zero — and in both project skills
      (`.claude/skills/import-rutetermin/SKILL.md`,
      `.claude/skills/verify-turnus-data/SKILL.md`) plus the CLAUDE.md
      "Turnus Data" section.
   7. Extend `tests/test_protected_files.py` with an assertion that
      `app/static/turnusfiler` no longer exists, so the tree can't quietly
      come back.
   8. Prod deploy: move the directory on the server, and check the nginx
      config — if a `location /static` block serves the old path directly,
      nothing extra is needed after the move, but confirm no separate alias
      points at `turnusfiler`.

   **Verify.** Full suite (+1 for the guard test); then logged-out `curl`
   against a schedule JSON, a PNG and the turnus PDF URL → all 302/401, and
   logged-in downloads still work (dropdown, strekliste images,
   /download_pdf).

---

## Explicitly NOT problems (don't "fix" these)

- File serving in `api.py::get_shift_image` — already traversal-safe
  (`os.path.basename` + `glob.escape`).
- Login flash messages revealing stub/NLF/unverified state — only shown
  after a correct password; acceptable.
- Søknadsskjema 71-row truncation — CLOSED by Solve 2026-07-12, keep as is.
- Kompdag counting rules, strekliste geometry, hours-tolerance bands —
  calibrated and test-asserted; leave alone.
- The synchronous per-page-view `UserActivity` insert — fine at current
  scale; retention cleanup exists.

## Definition of done (per task)

- `venv/bin/pytest -q` → 368+ passed, 0 failed (count grows with new tests).
- New behavior covered by at least one test where the task says so.
- No changes outside the files the task names, unless a grep proved another
  call site.
- Phase 2 tasks: a short written summary of options given to Solve, no code
  changes until an option is chosen.
