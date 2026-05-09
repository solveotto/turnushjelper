# Site Map — Turnushjelper

Generated 2026-05-08. Update whenever routes are added or removed.

---

## Auth blueprint (`app/routes/auth.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET/POST | `/login` | No | Login form. POST validates credentials, writes tour flags to session, redirects to `/`. |
| GET | `/logout` | Yes | Clears session, logs activity event, redirects to `/login`. |
| GET/POST | `/forgot-password` | No | Request password reset. POST sends reset email via Mailgun. |
| GET/POST | `/reset-password/<token>` | No | Reset password using token from email. |

---

## Registration blueprint (`app/routes/registration.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET/POST | `/register` | No | Self-registration form (rate-limited: 10 POST/hour). Checks `AuthorizedEmails` for rullenummer, creates stub user, sends verification email. |
| GET | `/verify/<token>` | No | Activates account via email token; sets `email_verified=1` on `DBUser`. |
| GET/POST | `/resend-verification` | No | Resends the verification email for an unverified account. |

---

## Shifts blueprint (`app/routes/shifts.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/` | Yes | Redirects to landing page configured by `AppConfig.LANDING_PAGE` (default: `turnusliste`). |
| GET | `/turnusliste` | Yes | Main turnus table. Renders all shifts for the user's selected turnus set. Heavy page — cached per user+turnus_set. |
| GET | `/switch-year/<int:turnus_set_id>` | Yes | Changes the user's selected turnus set in session; redirects to `/turnusliste`. |
| GET | `/favorites` | Yes | Shows the user's favorited shifts with weekly calendar view. |
| GET | `/oversikt` | Yes | Compare statistics across multiple turnus years. Reads from multiple `TurnusSet` DataframeManagers. |
| GET | `/mintur` | Yes | Personalised view for the user's own shift based on their `Innplassering` record. Redirects to `/turnusliste` if no innplassering. |
| GET | `/mintur/export_ical` | Yes | Downloads an `.ics` calendar file of the user's own shifts. |
| GET | `/turnusnokkel/<int:turnus_set_id>/<turnus_name>` | Yes | Shift key view (turnusnøkkel) for a named shift. |
| GET+POST | `/soknadsskjema` | Yes | Application form (søknadsskjema). GET renders it; POST saves choices to `SoknadsskjemaChoice`. Generates downloadable Word/PDF. |
| GET | `/import-favorites` | Yes | Import favorites from another turnus set. Renders preview of matches. |

---

## Downloads blueprint (`app/routes/downloads.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/download_pdf` | Yes | Serves a PDF file from `static/turnusfiler/`. Filename passed as query param. |

---

## Minside blueprint (`app/routes/minside.py`) — prefix: `/minside`

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/minside/` | Yes | User profile page showing account info, rullenummer, stasjoneringssted. |
| POST | `/minside/change-password` | Yes | Changes the user's password after verifying current password. |

---

## API blueprint (`app/routes/api.py`) — prefix: `/api`

| Method | URL | Login required | What it does |
|---|---|---|---|
| POST | `/api/toggle_favorite` | Yes | Add/remove a shift from favorites. Returns updated favorites list + positions dict for DOM update. |
| POST | `/api/move-favorite` | Yes | Reorder a favorite (drag-drop). Updates `order_index` in DB. |
| POST | `/api/set-favorite-position` | Yes | Set a favorite to a specific position. |
| POST | `/api/generate-turnusnokkel` | Yes | Generate turnusnøkkel PDF/Word for a shift. |
| POST | `/api/import-favorites-preview` | Yes | Preview which favorites can be imported from another turnus set. |
| POST | `/api/import-favorites-confirm` | Yes | Confirm and apply the favorites import. |
| GET | `/api/get-turnus-sets-for-import` | Yes | List turnus sets available for favorites import. |
| GET | `/api/shift-image/<int:turnus_set_id>/<shift_nr>` | No | Serve a strekliste image file. |
| POST | `/api/mark-tour-seen` | Yes | Mark a named guided tour as completed. Writes to `DBUser.has_seen_*` column. |
| POST | `/api/soknadsskjema-choice` | Yes | Save a soknadsskjema checkbox selection to `SoknadsskjemaChoice`. |
| GET | `/api/check-rullenummer` | No | Check if a rullenummer exists in `AuthorizedEmails`. Used during registration. |

---

## Admin blueprint (`app/routes/admin.py`) — prefix: `/admin`, admin-only

| Method | URL | What it does |
|---|---|---|
| GET | `/admin/dashboard` | Overview: user counts, turnus sets, PDF upload status. |
| GET | `/admin/activity` | Activity log — last 200 events + per-user stats. |
| POST | `/admin/reset-tour` | Reset all guided tour flags to 0 for all users. Clears full cache. |
| GET/POST | `/admin/create_user` | Create a new user directly (admin bypass of self-registration). |
| GET/POST | `/admin/edit_user/<int:user_id>` | Edit user details (name, email, rullenummer, etc.). |
| POST | `/admin/delete_user/<int:user_id>` | Delete a user. |
| POST | `/admin/toggle_auth/<int:user_id>` | Toggle admin status for a user. |
| GET | `/admin/turnus-sets` | List all turnus sets; shows status of turnusnøkkel, innplassering, strekliste. |
| GET/POST | `/admin/create-turnus-set` | Create a turnus set by uploading a PDF. Runs `shiftscraper` to extract JSON. |
| POST | `/admin/switch-turnus-set` | Set a turnus set as the global active set. |
| POST | `/admin/refresh-turnus-set/<int:turnus_set_id>` | Re-run the PDF scraper on an existing set. |
| GET | `/admin/turnusnokkel-status/<int:turnus_set_id>` | JSON: check if turnusnøkkel file exists for set. |
| POST | `/admin/upload-turnusnokkel/<int:turnus_set_id>` | Upload a turnusnøkkel Excel file. |
| GET | `/admin/innplassering-status/<int:turnus_set_id>` | JSON: check if innplassering data exists for set. |
| POST | `/admin/import-innplassering/<int:turnus_set_id>` | Import innplassering from Excel file. |
| POST | `/admin/delete-turnus-set/<int:turnus_set_id>` | Delete a turnus set and all its data. |
| GET | `/admin/authorized-emails` | List all authorized rullenummer entries. |
| POST | `/admin/add-authorized-email` | Add a single authorized rullenummer. |
| POST | `/admin/delete-authorized-email/<int:email_id>` | Remove an authorized rullenummer. |
| POST | `/admin/bulk-add-emails` | Bulk-add authorized rullenummer entries from text. |
| GET | `/admin/strekliste-status/<int:turnus_set_id>` | JSON: check if strekliste images exist for set. |
| POST | `/admin/upload-strekliste/<int:turnus_set_id>` | Upload strekliste PDF and generate timeline images. |
| POST | `/admin/generate-strekliste/<int:turnus_set_id>` | Re-generate strekliste images from existing PDF. |
| POST | `/admin/delete-strekliste-images/<int:turnus_set_id>` | Delete generated strekliste images. |
| GET | `/admin/user/<int:user_id>` | Detailed user view: activity log, favorites, innplassering. |
| GET | `/admin/employees` | List all employees (stub + registered). |
| POST | `/admin/import-employees` | Import employees from Excel. |
| POST | `/admin/upload-ansinitet` | Upload ansienitet PDF. |
| POST | `/admin/sync-employees` | Sync stub users against imported employee list. |
| POST | `/admin/add-employee` | Add a single employee manually. |
| POST | `/admin/cleanup-missing-stubs` | Remove stub users with no matching employee record. |
| POST | `/admin/reset-to-stub/<int:user_id>` | Downgrade a registered user back to stub. |
| POST | `/admin/delete-employee/<int:user_id>` | Delete an employee record entirely. |

---

## Database models (`app/models.py`)

| Model | Table | Purpose |
|---|---|---|
| `DBUser` | `users` | User account — credentials, rullenummer, tour flags, stasjoneringssted |
| `AuthorizedEmails` | `authorized_emails` | Whitelist of rullenummer allowed to self-register |
| `EmailVerificationToken` | `email_verification_tokens` | Email verification and password-reset tokens |
| `TurnusSet` | `turnus_sets` | A named turnus year (e.g. "T25") with associated file paths |
| `Favorites` | `favorites` | User's favorited shifts per turnus set, with order |
| `Shifts` | `shifts` | Shift titles per turnus set (populated from PDF scrape) |
| `SoknadsskjemaChoice` | `soknadsskjema_choices` | User's checkbox selections on the application form |
| `UserActivity` | `user_activity` | Page view and login/logout events |
| `Innplassering` | `innplassering` | Which shift a rullenummer is assigned to in a turnus set |

---

## Services (`app/services/`)

| File | Responsibility |
|---|---|
| `user_service.py` | User CRUD, password hashing, stub management |
| `auth_service.py` | Login, tokens, password reset, authorized email management |
| `turnus_service.py` | TurnusSet CRUD, active set management |
| `favorites_service.py` | Favorites add/remove/reorder per user+turnus_set |
| `activity_service.py` | Log and query user activity events |
| `innplassering_service.py` | Read innplassering records for a user |
