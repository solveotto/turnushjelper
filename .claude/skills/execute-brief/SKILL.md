---
name: execute-brief
description: Use when executing an implementation brief, fix list, or follow-up document in this repo (TODO_*.md, review follow-ups, handoff briefs) — before opening any file the brief names.
---

# Execute a fix-brief the house way

## Overview

Briefs are how Solve delegates work to agents. The brief says *what*; this
skill is the standing *how*. It applies to every brief even when the brief
doesn't repeat these rules.

**Violating the letter of these rules is violating their spirit.**

## Before the first task

1. Read `CLAUDE.md` in full (three-layer architecture, raw-SQLAlchemy session
   pattern, Norwegian UI / English code, venv/bin commands).
2. Baseline: `venv/bin/pytest -q` must pass **before you change anything**.
   Record the count. Any new failure you introduce is yours to fix before
   moving on.
3. Read the whole brief. Classify each item: *implement now* vs *needs a
   decision from Solve* (a brief may mark these itself, e.g. "Part 2").

## While executing

- **Locate code by quoted snippet, not line number.** Line numbers drift the
  day after a brief is written; snippets don't.
- **Read every file before editing it** — the surrounding context, not just
  the target lines.
- **Decision items are presented, never implemented.** Summarize the options
  for Solve and move on. This includes anything ambiguous enough that you'd
  be choosing product behavior.
- **Stay inside the files the brief names**, unless a grep proves another
  call site (then say so in the report).
- **Protected areas — do not touch unless the brief explicitly says to:**
  - kompdag counting rules (`app/utils/kompdag_utils.py`; reference counts
    asserted in `tests/test_kompdag_routes.py`)
  - strekliste geometry (`app/utils/pdf/strekliste_generator.py`;
    `tests/test_strekliste_geometry.py`)
  - regenerating `turnus_stats_*.json` (only when
    `tests/test_shift_stats.py::test_stored_stats_match_fresh_computation`
    fails)
- **Never commit or push.** Solve commits.
- Run `venv/bin/pytest -q` after **every** task, not once at the end.

## Rationalizations that mean STOP

| Excuse | Reality |
|---|---|
| "The line number in the brief points here" | Numbers drift. Match the quoted snippet or grep for it. |
| "This failure was probably pre-existing" | The baseline run proves otherwise. You broke it; fix it. |
| "Too small a change to re-run the suite" | The suite is ~2 minutes. A silent break costs hours. |
| "Option A is obviously right, I'll just do it" | Decision items are Solve's. Present, don't implement. |
| "While I'm here, I'll clean this up too" | Out-of-scope edits invalidate the brief's review. Note it in the report instead. |
| "The stats JSON looks stale, I'll regenerate" | Only the freshness test failing justifies regeneration. |

## Report format (end of run)

One line per brief item: **done** (what changed, which test covers it) /
**blocked** (why, what's needed) / **decision needed** (options summarized).
Then the final `venv/bin/pytest -q` count vs the baseline count.
