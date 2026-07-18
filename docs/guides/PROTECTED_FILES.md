# Protected files (PII) — storage scheme and deploy migration

**Since 2026-07-18**, files containing member/employee personal data are stored
in `instance/protected/` (`AppConfig.protected_dir`) instead of
`app/static/turnusfiler/`. Everything under `app/static/` is served over HTTP
**without authentication** by both Flask and nginx, so PII must never live
there. `tests/test_protected_files.py` enforces this (no PII patterns under
static, none tracked by git, all path helpers resolve outside static).

Affected files:

| File | Used by | Path helper (`app/utils/protected_paths.py`) |
|---|---|---|
| `medlemsliste.xlsx` | NLF member import (admin) | `member_excel_path()` |
| `ansinitet.pdf` | Seniority-list sync (admin) | `ansinitet_pdf_path()` |
| `{rxx}/innplassering_{YEAR}.pdf` | Innplassering import (admin + `scripts/import_innplassering.py`) | `innplassering_pdf_path(year_id)` |

Layout: organization-wide files (`medlemsliste.xlsx`, `ansinitet.pdf` — one of
each, not tied to a turnus set) live at the root; per-turnus-set files live in
a per-set subdir mirroring the `turnusfiler/{rxx}/` convention:

```
instance/protected/
├── medlemsliste.xlsx
├── ansinitet.pdf
├── r26/innplassering_R26.pdf
└── r27/innplassering_R27.pdf     (when R27 arrives)
```

The admin upload routes create `instance/protected/` automatically on the next
upload — no manual setup is needed for new files. `instance/` is gitignored, so
these files can never re-enter the repository.

## One-time migration on the production server

The code now reads **only** the new location. After deploying, move the
existing files (paths relative to the app root):

```bash
mkdir -p instance/protected/r26
mv app/static/turnusfiler/medlemsliste.xlsx        instance/protected/ 2>/dev/null
mv app/static/turnusfiler/ansinitet.pdf            instance/protected/ 2>/dev/null
mv app/static/turnusfiler/r26/innplassering_R26.pdf instance/protected/r26/ 2>/dev/null
sudo systemctl restart turnushjelper
```

Skipping the `mv` is safe but degrades gracefully: the admin pages will show
"PDF ikke funnet" / "Ingen lagret medlemsliste funnet" until the files are
re-uploaded through the admin UI. Do **not** leave the old copies behind under
`app/static/` — that is the exposure this change removes.

Verify after restart:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/static/turnusfiler/medlemsliste.xlsx   # → 404
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/static/turnusfiler/ansinitet.pdf       # → 404
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/static/turnusfiler/r26/innplassering_R26.pdf  # → 404
```

Optional nginx belt-and-braces (blocks the whole class even if a PII file is
ever misplaced again):

```nginx
location ~* ^/static/turnusfiler/.*(medlemsliste|ansinitet|innplassering) {
    return 404;
}
```

## Purging medlemsliste.xlsx from git history

`medlemsliste.xlsx` was **tracked in git and pushed to origin** before this
change; removing it from the working tree does not remove it from history.
Purging requires rewriting history and force-pushing, which breaks every
existing clone — including the production server if it pulls from origin.
**Coordinate this manually; do not script it into auto-deploy:**

```bash
pip install git-filter-repo
git filter-repo --invert-paths --path app/static/turnusfiler/medlemsliste.xlsx
git remote add origin <origin-url>       # filter-repo removes the remote
git push --force origin main
# then on the server and every clone: re-clone, or
# git fetch && git reset --hard origin/main
```

Until the purge is done, treat the repository itself as containing member PII:
keep the origin remote private and don't add collaborators or mirrors.
