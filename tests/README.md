# Tests — Shift Rotation Organizer

## Quick Start

```bash
# Run all tests
venv/bin/pytest -v

# Run a specific test file
venv/bin/pytest tests/test_auth_routes.py -v

# Run load tests with output
venv/bin/pytest tests/test_load.py -v -s

# Load test against PythonAnywhere
LOAD_TEST_URL=https://yourapp.pythonanywhere.com venv/bin/pytest tests/test_load.py -v -s
```

## Project Structure

```
tests/
├── conftest.py                 # Shared fixtures (app, client, db, seed data)
├── test_models.py              # Database model constraints and queries
├── test_user_service.py        # User CRUD operations
├── test_auth_service.py        # Email verification, tokens, password reset
├── test_favorites_service.py   # Add/remove/list favorites
├── test_turnus_service.py      # Turnus set lifecycle and cascading deletes
├── test_auth_routes.py         # Login page rendering and login flow
├── test_api_routes.py          # /toggle_favorite API endpoint
├── test_load.py                # Concurrent load / stress tests
└── README.md                   # This file
```

## Fixtures (conftest.py)

All tests share an **in-memory SQLite** database with per-test transaction rollback, so every test starts with a clean slate.

| Fixture | Scope | Description |
|---------|-------|-------------|
| `test_engine` | session | In-memory SQLite engine, tables created once |
| `db_session` | function | Session with transaction rollback after each test |
| `patch_db` | function | Monkeypatches `get_db_session` across all service modules |
| `app` | function | Flask app with `TESTING=True`, CSRF disabled |
| `client` | function | Flask test client |
| `sample_user` | function | Regular user — `testuser` / `password123` |
| `admin_user` | function | Admin user — `adminuser` / `adminpass123` |

Helper: `login_user(client, username, password)` — logs in via POST to `/login`.

## Load Test Configuration

The load tests in `test_load.py` support two modes and are tunable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOAD_TEST_URL` | *(empty)* | Set to a URL to switch to remote mode |
| `LOAD_TEST_WORKERS` | `10` | Number of concurrent threads |
| `LOAD_TEST_REQUESTS` | `50` | Number of requests per test |

```bash
# Example: higher concurrency
LOAD_TEST_WORKERS=20 LOAD_TEST_REQUESTS=100 venv/bin/pytest tests/test_load.py -v -s
```

---

# Test Plan

## Layer 1 — Models (`test_models.py`)

Tests that the SQLAlchemy models enforce database-level constraints.

| Test | Validates |
|------|-----------|
| `test_create_and_query` | DBUser insert and retrieval |
| `test_unique_username` | Duplicate usernames raise IntegrityError |
| `test_unique_year_identifier` | Duplicate turnus set year identifiers rejected |
| `test_unique_constraint` (Favorites) | Duplicate user+shift+turnus_set rejected |
| `test_verify_password` | UserWrapper password hashing roundtrip |

## Layer 2 — Services

### User Service (`test_user_service.py`)

| Test | Validates |
|------|-----------|
| `test_create_user` | Successful user creation |
| `test_create_user_duplicate` | Duplicate username returns error message |
| `test_get_user_data` | Retrieval by username |
| `test_get_user_data_missing` | Returns None for unknown user |
| `test_delete_user` | User deletion and confirmation |
| `test_update_user_password` | Password change, old invalid, new valid |

### Auth Service (`test_auth_service.py`)

| Test | Validates |
|------|-----------|
| `test_add_and_check` | Authorized email whitelist |
| `test_create_and_verify` | Email verification token flow |
| `test_verify_expired_token` | Expired tokens rejected with message |
| `test_full_reset_flow` | Password reset token creation and usage |

### Favorites Service (`test_favorites_service.py`)

| Test | Validates |
|------|-----------|
| `test_add_and_get` | Add multiple favorites, correct ordering |
| `test_remove_favorite` | Favorite removal |
| `test_add_duplicate_is_idempotent` | No duplicates on repeated adds |
| `test_get_max_ordered_index` | Returns highest order index or 0 |

### Turnus Service (`test_turnus_service.py`)

| Test | Validates |
|------|-----------|
| `test_create_and_get_by_year` | Turnus set creation and retrieval |
| `test_set_active_deactivates_others` | Only one active turnus set at a time |
| `test_delete_cascades` | Delete cascades to shifts and favorites |

## Layer 3 — Routes

### Auth Routes (`test_auth_routes.py`)

| Test | Validates |
|------|-----------|
| `test_login_page_renders` | GET `/login` returns 200 with expected content |
| `test_login_success` | Correct credentials redirect (302) |
| `test_login_wrong_password` | Wrong password shows error |

### API Routes (`test_api_routes.py`)

| Test | Validates |
|------|-----------|
| `test_requires_login` | Unauthenticated POST redirects to login |
| `test_add_favorite` | Authenticated toggle adds a favorite |
| `test_remove_favorite` | Authenticated toggle removes a favorite |

## Layer 4 — Load / Stress (`test_load.py`)

| Test | Requests | Validates |
|------|----------|-----------|
| `test_concurrent_login_page` | 50 GET `/login` | Zero 5xx, p95 < 2s |
| `test_concurrent_login_attempts` | 20 POST `/login` | Zero 5xx under bad-credential flood |
| `test_concurrent_toggle_favorite` | 20 POST (local only) | Thread safety, zero 5xx |
| `test_sustained_mixed_traffic` | 100 mixed waves | Error rate and p95 < 3s |

## Coverage Gaps (Known)

The following areas are **not yet covered** and are candidates for future tests:

- **Admin routes** — user management, turnus uploads
- **Registration flow** — signup, email verification end-to-end
- **PDF utilities** — shift scraper, double-shift scanner, strekliste generator
- **Minside routes** — profile page, password change via UI
- **Shift routes** — shift listing, filtering
- **Main routes** — landing page, static pages
- **CSRF protection** — currently disabled in tests
- **Remote-mode load tests** — require a running PythonAnywhere deployment
