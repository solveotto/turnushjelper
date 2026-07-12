# Brain-dump: project skills I want built

> Drafted by Claude on 2026-07-12 from repo context (CLAUDE.md, memory notes,
> TODO_remaining_fixes.md, turnus_scraping_hardening_plan.md, scripts/) as a
> strawman of what Solve would have written. Items marked **[GUESS]** are
> inferences Solve has not confirmed — correct or delete them before building.
>
> Goal for all of these: a lower-tier model should be able to run the job the
> way I would — same ground rules, same verification, same paranoia about
> turnus data correctness.

## 1. `import-rutetermin` — onboard a new rutetermin (R27, R28, …)

**What it does.** Walks through everything needed when a new rutetermin's
source files arrive, in order:

1. Place source files in `app/static/turnusfiler/{rXX}/` (Timeskjema `.xls`
   export — really ISO-8859-1 TSV — plus the turnus PDF, innplassering PDF,
   streker PDF, and `turnusnøkkel_{YEAR}_org.xlsx`).
2. Parse the TSV as the primary source; run the PDF scraper as
   cross-verification. Never hard-fail on differences — sources can be
   different planning revisions (R26 differed in 20 cells); produce a diff for
   me to adjudicate.
3. Everything goes through `validate_turnus_json` before being written.
4. Regenerate `turnus_stats_{ID}.json`, double-shift data, and strekliste PNGs
   (geometry auto-calibrates; covered by `tests/test_strekliste_geometry.py`).
5. Re-derive kompdag reference counts for the new rutetermin and add them to
   `tests/test_kompdag_routes.py` the way R26's `[4, 1, 3, 2, 2, 4]` is
   asserted.
6. Create the TurnusSet in the DB (`scripts/create_new_turnus_year_in_database.py`
   or the admin UI — the skill should know which one is current) and import
   innplassering (`scripts/import_innplassering.py`).
7. Full `venv/bin/pytest -q` at the end; report what was produced and every
   diff/anomaly found on the way.

**Why it matters to me.** This is the single most important recurring job and
it happens rarely enough (about once a year) that the traps get forgotten:
the accounting-week grouping in the TSV, the `&` suffixes, the wrong
`Ruteterminperiode:` header, the kl_timer tolerance band. The app's whole
value is that this data is correct. All of the traps are written down
(CLAUDE.md "Turnus Data Sources & Ingestion") — the skill turns them into a
checklist so I don't have to remember them.

**Confirmed (Solve, 2026-07-12):** Timeskjema TSV will be the main import
path in the future, but `ny_shift_ingress` is not ready to merge yet. Build
the skill PDF-first for now, structured so the TSV steps slot in when the
branch merges — the validator gate, cross-source diff, regeneration, and
kompdag steps are identical either way. The skill should state this status
explicitly so a future agent checks whether `ny_shift_ingress` has landed
before assuming PDF is still primary.

## 2. `verify-turnus-data` — on-demand data integrity sweep

**What it does.** Read-only check of the active turnus sets: run
`validate_turnus_json` over the schedule JSONs, confirm stored stats match
fresh computation (same check as
`tests/test_shift_stats.py::test_stored_stats_match_fresh_computation`),
confirm kompdag counts still match the asserted references, run the hours
cross-check, and flag anything off (like the known `OSL_01` W1D1 start/slutt
malformation class). Report findings; change nothing.

**Why it matters to me.** Silent data corruption is the nightmare scenario —
the R26 W1D1 malformation sat unnoticed because a downstream consumer happened
to recompute around it. I want a single command I (or a scheduled agent) can
run after any import, refactor, or "it looks wrong" report from a colleague.

## 3. `execute-brief` — run a fix-brief the house way

**What it does.** Takes an implementation brief in the
`TODO_remaining_fixes.md` format and executes it under the standing ground
rules: read CLAUDE.md first, `venv/bin/` for everything, baseline
`venv/bin/pytest -q` before starting and after every task, locate code by
quoted snippet not line number, read every file before editing, never touch
the protected areas (kompdag counting rules, strekliste geometry, stats
regeneration) unless the brief explicitly says to, present Part-2-style
decision items to me instead of implementing them, and never commit unless I
ask. Ends with a per-task done/skipped/blocked report.

**Why it matters to me.** This is exactly how I want to delegate work to
lower-tier agents after losing access to the bigger model: I (or a review
session) write the brief, a cheaper agent executes it. The ground rules are
currently re-written into each brief by hand; the skill makes them standing
policy so briefs can be shorter and nothing gets dropped.

**Companion (maybe fold in):** `write-brief` — after a review/debug session,
produce the brief itself in the same format (ground rules section, quoted
snippets, per-task verify steps, Part 1/2/3 split by decision-need).

## 4. `prod-ops` — server deploy and maintenance round

**What it does.** **[GUESS — mechanics unconfirmed.]** The recurring
production chores as one guided checklist: deploy the current main to the
server (git pull + gunicorn restart? — commits like "server updated" suggest a
manual routine only I know), verify the app responds afterwards, check that
`scripts/backup/daily_mysql_backup.py` and the offsite copy are current (or
run `test_backup_system.py`), and run the cleanup jobs
(`cleanup_unverified_users.py`, `cleanup_activity_log.py`,
`db_check_orphaned_favorites.py` → `db_cleanup_orphaned_favorites.py` only
after reviewing what check found).

**Why it matters to me.** These live entirely in my head and shell history.
If someone else (or an agent) has to keep the site alive, there is currently
no written procedure — this one is as much documentation as automation.

**Open questions for me to answer before building:** how deploys actually
happen (ssh target, service manager, any downtime rules), where backups land
and how to tell "current" from "stale", and whether cleanups are safe to run
unattended.

## Not skills (already handled elsewhere)

- Kompdag rules, strekliste geometry, session/cache patterns — encoded in
  CLAUDE.md and locked by tests.
- Code review — the code-review plugin covers it.
- Permission/PATH guardrails — venv-guard hook in `.claude/settings.json`.

## Priority if building in order

1 and 3 first (highest value, best understood), then 2 (mostly a subset of
1's verification steps, extracted), then 4 (blocked on my answers anyway).
