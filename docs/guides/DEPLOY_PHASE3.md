# Phase 3 deploy runbook — staging, then production

One-off runbook for the Phase 3 backlog (items 4–8) plus the earlier undeployed
work sitting on `main`. Delete this file once both servers are on the final
state.

Server layout assumed: repo at `/home/deploy/turnushjelper`, venv at
`venv/`, app run by a systemd unit. Confirm the unit name once and reuse it:

```bash
systemctl list-units --type=service | grep -i turnus
```

Everything below writes it as `turnushjelper.service`.

---

## Why two passes

**Pass A** = everything already on `main` (`55712d3`): page-cache removal,
Pillow 12.3.0, the `user_service` split, items 4–7.
**Pass B** = item 8, the move of the turnus data store out of `app/static/`.

They are deployed separately on purpose:

- Pass A carries the pickle→JSON session change (`27914a1`, Task 2.3).
  Production has never run it. **The restart logs out every user, including
  you.** Staging already absorbed this.
- Pass B moves files on disk. `git pull` relocates only the 11 **tracked**
  data files; the ~844 gitignored ones (strekliste PNGs, source PDFs) stay at
  the old path. A plain pull leaves a split tree.
- Pass B's failure mode is quiet: `DataframeManager` logs "Turnus file not
  found", falls back, and serves an **empty DataFrame**. The site loads and
  looks fine, just with no turnus data. Bundled with Pass A, a regression could
  come from either and this symptom is easy to misattribute.

Verify each pass on production before starting the next.

---

## Step 0 — locally, before touching any server

Item 8 is still uncommitted on `phase3-move-turnusdata`. Commit it, but **do
not merge it to `main` yet** — `main` must stay at `55712d3` for the duration of
Pass A.

```bash
cd ~/projects/turnushjelper
venv/bin/pytest                 # expect 386 passed
git add -A
git add -f turnusdata/r25/double_shifts_r25.json turnusdata/r26/double_shifts_r26.json
```

The `git add -f` line matters: both `double_shifts_*.json` files are
force-tracked despite matching `turnusdata/**/double_shifts_*.json` in
`.gitignore`. Without it, `git add -A` stages them as pure deletions. Check
before committing:

```bash
git diff --cached --name-status -- '*double_shifts*'   # both must be R100 (rename), not D
git ls-files turnusdata | wc -l                        # must be 11
```

Expected:

```
R100  app/static/turnusfiler/r25/double_shifts_r25.json  turnusdata/r25/double_shifts_r25.json
R100  app/static/turnusfiler/r26/double_shifts_r26.json  turnusdata/r26/double_shifts_r26.json
```

Do not use `--stat` for this check: it truncates the path prefix to `...`, so a
rename and a deletion look nearly identical.

Then commit and push the branch:

```bash
git commit -F - <<'EOF'
Move the turnus data store out of app/static/ (Phase 3 item 8)

Nothing under app/static/ is authenticated. api.get_shift_image and
downloads.download_pdf were @login_required, but the identical bytes were
fetchable at /static/turnusfiler/... with no session — protection that did not
protect. The data store now lives at turnusdata/ (AppConfig.turnusfiler_dir),
outside app/, and is only reachable through the authed routes.

- config.py: turnusfiler_dir now resolves to <root>/turnusdata
- new route downloads.download_turnus_pdf (/download/pdf/<filename>),
  @login_required, basename-sanitized, .pdf-only; the PDF dropdown in
  app/__init__.py no longer builds a /static/ URL
- df_utils: TurnusSet rows store ABSOLUTE paths, so the move stranded every
  row. DataframeManager now falls back to the conventional location and logs a
  warning instead of silently serving an empty DataFrame
- scripts/repoint_turnus_paths.py makes the DB truthful again (idempotent,
  --dry-run)
- .gitignore rules repointed; both double_shifts_*.json stay force-tracked
- tests/test_protected_files.py gains test_turnusfiler_is_not_under_static —
  a structural guard, unlike the PII filename denylist, which fails open
- docs, skills and templates updated to the new path; PROTECTED_FILES.md keeps
  its historical app/static/turnusfiler paths on purpose (the git filter-repo
  invocation needs the path history actually contains)

386 passed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF

git push -u origin phase3-move-turnusdata
```

---

## Pass A — deploy current `main` (`55712d3`)

### A1. Staging

```bash
ssh <staging>
cd /home/deploy/turnushjelper

git log -1 --oneline                      # record this SHA — it is your rollback target
git pull                                  # expect 55712d3
venv/bin/pip install -r requirements.txt  # a pull alone does not install Pillow 12.3.0
venv/bin/alembic upgrade head             # no-op if already current
sudo systemctl restart turnushjelper      # required — a running worker never reloads changed code
```

### A2. Verify staging

```bash
venv/bin/pip show pillow | grep Version   # 12.3.0
sudo systemctl status turnushjelper       # active (running), no traceback
sudo journalctl -u turnushjelper --since "2 min ago" | tail -30
```

In a browser:

1. Log in (your old session is dead — that is expected).
2. Sessions are JSON now, not pickle:
   ```bash
   venv/bin/python -c "from app.database import SessionLocal; from app.models import FlaskSessionModel; r=SessionLocal().query(FlaskSessionModel).order_by(FlaskSessionModel.id.desc()).first(); import json; json.loads(r.data); print('OK', len(r.data))"
   ```
   Exit 0 and `OK` means the change took.
3. **The favorites fix** — this is the bug that started all of it, and it is
   only observable with ≥2 workers. Toggle a favourite, then reload
   `/turnusliste` six or eight times. The star and the `#N` pill must stay
   stable every single time. If they flicker, the old cache is still live.
4. `/soknadsskjema` still generates a document (item 7 moved the builders into
   `app/utils/soknadsskjema_gen.py`).
5. `/oversikt` renders and the metric cells are populated (item 5 escaped the
   interpolated values — a broken escape shows literal `&lt;span&gt;`).

### A3. Production

Same commands as A1. **Pick a quiet window** — the restart is the moment every
session dies — and have your own credentials to hand.

```bash
ssh <prod>
cd /home/deploy/turnushjelper

git log -1 --oneline                      # record — Pass A rollback target
git pull
venv/bin/pip install -r requirements.txt
venv/bin/alembic upgrade head
sudo systemctl restart turnushjelper
```

### A4. Verify production

Repeat A2 against production. Additionally, before starting Pass B, confirm the
exposure item 8 exists to fix is genuinely open right now — these should return
**200**:

```bash
curl -sI https://<prod-host>/static/turnusfiler/r26/turnus_schedule_R26.json | head -1
curl -sI https://<prod-host>/static/turnusfiler/r26/streklister/png/1426.png | head -1
```

A 200 here is the finding. Pass B turns both into 404.

### A5. Rollback (Pass A)

```bash
git checkout <recorded-sha>
venv/bin/pip install -r requirements.txt
sudo systemctl restart turnushjelper
```

Sessions log out once more. Nothing on disk changed, so there is nothing else
to undo.

---

## Merge item 8

Only after production is verified on Pass A:

```bash
cd ~/projects/turnushjelper
git checkout main
git merge phase3-move-turnusdata
git push
```

---

## Pass B — the data-store move

Order matters: **pull first, then relocate the leftovers.** Moving before the
pull risks git refusing to overwrite untracked files.

### B0. Pre-check — PII must not ride along

If this server never ran the 2026-07-18 migration in
`docs/guides/PROTECTED_FILES.md`, member PII is still sitting under
`app/static/turnusfiler/` and the `rsync` below would drag it into
`turnusdata/`. Get it out first:

```bash
cd /home/deploy/turnushjelper
find app/static/turnusfiler -iname 'medlemsliste*' -o -iname 'ansinitet*' -o -iname 'innplassering*'
```

If that prints anything:

```bash
mkdir -p instance/protected/r26
mv app/static/turnusfiler/medlemsliste.xlsx         instance/protected/ 2>/dev/null
mv app/static/turnusfiler/ansinitet.pdf             instance/protected/ 2>/dev/null
mv app/static/turnusfiler/r26/innplassering_R26.pdf instance/protected/r26/ 2>/dev/null
```

### B1. Record the invariant

```bash
find app/static/turnusfiler -type f | wc -l      # call this N
git log -1 --oneline                             # Pass B rollback target
```

After the move, `find turnusdata -type f | wc -l` must equal **N** — the 11
tracked files move out of `app/static/turnusfiler` and into `turnusdata/`, so
the total is preserved.

### B2. Deploy

```bash
git pull                       # tracked files land in turnusdata/; the rest stay behind

rsync -a app/static/turnusfiler/ turnusdata/
rm -rf app/static/turnusfiler

venv/bin/pip install -r requirements.txt
venv/bin/python scripts/repoint_turnus_paths.py --dry-run   # inspect
venv/bin/python scripts/repoint_turnus_paths.py
sudo systemctl restart turnushjelper
```

`repoint_turnus_paths.py` rewrites the **absolute** paths stored on `TurnusSet`
rows, which the move invalidated. The app tolerates stale ones — it falls back
to the conventional location and logs a warning — so this is about making the
DB truthful, not about keeping the site up. It is idempotent; re-running is
free.

### B3. Check nginx

```bash
grep -rn "turnusfiler\|static" /etc/nginx/sites-enabled/
```

What matters is that no `location`/`alias` still points at a `turnusfiler`
path, and that `/static` keeps serving `css/js/img` normally. The optional
PII rule documented in `PROTECTED_FILES.md`
(`^/static/turnusfiler/.*(medlemsliste|ansinitet|innplassering)`) is now dead
but harmless — keep it as defence-in-depth. Only if you changed something:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### B4. Strekliste files do not travel with git

The correct 54-page `r26_streker.pdf` and its 423 PNGs are gitignored, so each
server has whatever was uploaded to it. **Stale PNGs from a previous PDF look
correct until someone regenerates them** — check both servers:

```bash
md5sum turnusdata/r26/streklister/r26_streker.pdf   # want 9091cf5ee5b1fd5db797a6dc3ccf6888
ls turnusdata/r26/streklister/png | wc -l           # want 423
```

If the md5 differs, upload the correct PDF, then:

```bash
venv/bin/python -c "import app.utils.pdf.strekliste_generator as sg; print(sg.generate_all_images('r26', force=True)['total'])"
```

`force=True` clears the directory first, so a stale set cannot survive.

### B5. Verify

1. **The exposure is closed** — the point of the whole item. Both must now be
   **404**:
   ```bash
   curl -sI https://<host>/static/turnusfiler/r26/turnus_schedule_R26.json | head -1
   curl -sI https://<host>/static/turnusfiler/r26/streklister/png/1426.png | head -1
   ```
2. **Data is actually there** — this guards the quiet failure. Log in, open
   `/turnusliste`: turnus cards populated, kompdag badges present, not an empty
   list. Then:
   ```bash
   sudo journalctl -u turnushjelper --since "5 min ago" | grep -i "not found"
   ```
   Silence is the pass condition.
3. **Authed paths still work**: the PDF-downloads dropdown (now
   `/download/pdf/<filename>`, no longer a `/static/` URL), strekliste images on
   turnusliste, `/download_pdf`, `/mintur`, `/turnusnokkel/<id>/<turnus>`.
4. `find turnusdata -type f | wc -l` equals **N** from B1.
5. `app/static/` contains only `css/`, `js/`, `img/` (plus whatever else was
   already legitimate) — no `turnusfiler`.

### B6. Rollback (Pass B)

A code revert alone is **not** enough — git will not move the untracked files
back:

```bash
git checkout <recorded-sha>
mkdir -p app/static/turnusfiler
rsync -a turnusdata/ app/static/turnusfiler/
rm -rf turnusdata
venv/bin/python scripts/repoint_turnus_paths.py   # points the rows back
sudo systemctl restart turnushjelper
```

Note this re-opens the static exposure, which is the whole reason it is a
rollback of last resort rather than a routine escape hatch. Everything under
`turnusdata/` can also be re-uploaded or regenerated from the admin UI, so
fixing forward is usually the better call.

---

## Order of operations, condensed

| # | Where | What |
|---|---|---|
| 0 | local | commit item 8 to the branch; do **not** merge |
| 1 | staging | Pass A — pull `55712d3`, pip, alembic, restart, verify |
| 2 | prod | Pass A — same; **global logout**; verify; confirm the 200s |
| 3 | local | merge item 8 to `main`, push |
| 4 | staging | Pass B — PII pre-check, pull, rsync, rm, repoint, restart, verify |
| 5 | prod | Pass B — same; confirm the 404s |
| 6 | local | delete this file |
