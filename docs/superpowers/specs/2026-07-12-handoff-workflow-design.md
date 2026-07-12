# Handoff Workflow for Lesser Models — Design

**Date:** 2026-07-12
**Status:** Approved by user (brainstorming session)

## Problem

The user's access to top-tier models (Fable 5 / Mythos) is quota-limited. When quota runs
out mid-work, weaker models (Opus, Sonnet, Haiku) must be able to both **plan and execute**
work on this project and other projects — safely, like a junior developer taking over from
a senior. Observed/feared failure modes, all in scope:

1. **Scope creep** — touching files or making "improvements" beyond the task
2. **False success claims** — "done" without running verification, or ignoring failures
3. **Vague or wrong plans** — missing file paths, steps that assume wrong things
4. **Lost context between sessions** — no record of state/decisions, next session starts blind

## Solution overview

One **global skill** at `~/.claude/skills/handoff/` with two modes, plus a short hook in
each project's CLAUDE.md. The skill *tightens* the superpowers pipeline
(`writing-plans` / `executing-plans`) rather than replacing it; it only adds the
junior-specific guardrails and the handoff-document convention.

```
~/.claude/skills/handoff/
  SKILL.md                 — mode router, tier rules, work-mode protocol
  templates/HANDOFF.md     — handoff doc template
  templates/JOURNAL.md     — journal entry template
```

## Model tiers

| Tier | Models | Rules |
|------|--------|-------|
| 1 | Fable / Mythos | Owns **prepare mode**: updates `docs/HANDOFF.md` at session end or on request. Work mode optional. |
| 2 | Opus | May plan and execute. Work mode required for multi-step tasks. Plans use the junior template but do **not** need user pre-approval. |
| 3 | Sonnet / Haiku and below | Work mode always. May write plans, but every plan must be **approved by the user before execution starts**. Prefer executing existing plans over writing new ones. |

Tier is determined by the session's model identity (the model knows its own name).

## Triggering (belt and suspenders)

1. **Skill description** written so lesser models self-invoke it before multi-step work,
   and strong models invoke it for prepare mode at session end.
2. **CLAUDE.md hook** (~3 lines, per project) — the reliable trigger, since every model
   loads CLAUDE.md:

   > If you are not running as Fable/Mythos, invoke the `handoff` skill (work mode)
   > before planning or executing any multi-step task. Every model updates
   > `docs/HANDOFF.md` via the `handoff` skill (prepare mode) at session end.

## Prepare mode — `docs/HANDOFF.md`

One file per project. **Overwritten** (not appended) on each update. Required sections:

1. **Last updated** — date + which model wrote it
2. **Current state** — active branch, work in flight, uncommitted changes, failing tests
3. **Recent decisions** — last handful, each with the *why*
4. **Known traps** — project-specific gotchas; link to CLAUDE.md sections rather than
   repeating them
5. **Next steps** — prioritized; each tagged `[safe-junior]`, `[needs-plan]`, or
   `[senior-only]`
6. **Do not touch** — files/areas off-limits without asking
7. **Open questions** — unresolved items awaiting the user or a senior model

Companion `docs/JOURNAL.md`: append-only, newest entry first. One entry per completed
task: date, model, task name, files changed, verification command + result summary,
questions asked and the user's answers.

## Work mode — the junior protocol

**Orient** (before touching anything)
- Read `docs/HANDOFF.md`, the last ~5 `docs/JOURNAL.md` entries, and CLAUDE.md.
- If HANDOFF.md is missing: say so explicitly and ask the user whether to proceed.
- Classify the task: *execute existing plan* / *small fix* / *needs new plan*.
- Check the task's tag in HANDOFF.md next steps; `[senior-only]` → stop and ask.

**Plan** (only when a new plan is needed)
- Use superpowers:writing-plans if installed; the skill adds junior requirements on top.
- Every plan task must have: exact file paths, a runnable verification command, and an
  explicit *out of scope* line.
- Self-review checklist before presenting: no vague steps, no unnamed files, no
  "should work" language.
- Tier 3: present the plan to the user and block for approval before executing.

**Execute** (per task)
- Touch only files the task names. Needing another file is a question, not an edit.
- Run the task's verification command and paste its actual output before claiming done.
  No output → no done.
- Commit per task; append a `docs/JOURNAL.md` entry.

**Escalate**
- Anything ambiguous, unexpected, or design-flavored → `AskUserQuestion` immediately
  (the user is normally present while lesser models work). Record the Q&A in the journal.
- Never guess-and-continue.

**Close session**
- Update HANDOFF.md *Current state* and *Next steps* (all tiers), so the file never
  goes stale.

## Rollout

1. Build the skill in `~/.claude/skills/handoff/` following superpowers:writing-skills
   conventions.
2. Add the CLAUDE.md hook to this repo.
3. Run prepare mode once here → first real `docs/HANDOFF.md` for turnushjelper. It must
   capture: current branch state, the `ny_shift_ingress` parser work, the in-flight UX
   modernization plan (`docs/superpowers/plans/2026-07-12-ux-modernization.md`).
4. **Acceptance test:** user opens a fresh session with `/model sonnet` and gives it a
   small task. Pass = the model invokes the skill, reads the handoff, and follows the
   protocol (orient → classify → verify → journal).

Other projects: add the 3-line CLAUDE.md hook + run prepare mode once. The skill itself
is global, nothing else to install.

## Out of scope

- No changes to the superpowers plugin itself.
- No automation/hooks in settings.json — triggering is via skill description + CLAUDE.md.
- No per-project copies of the skill.
- This repo's existing local skills (`execute-brief`, `import-rutetermin`,
  `verify-turnus-data`) are unchanged; work mode simply directs models to use them when
  they apply.
