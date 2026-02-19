# Database Migrations with Alembic

Alembic is the **sole schema manager** for this project. All table creation and schema changes go through migration files in `migrations/versions/`.

## Quick Reference

| Command | Description |
|---|---|
| `alembic upgrade head` | Apply all pending migrations (use for fresh install or updates) |
| `alembic current` | Show which revision the database is at |
| `alembic history` | List all migration revisions in order |
| `alembic downgrade -1` | Roll back the most recent migration |
| `alembic upgrade head --sql` | Print SQL without executing (dry run) |

## Fresh Install (New Database)

Run from the project root:

```bash
alembic upgrade head
```

This creates all tables from scratch by running every migration in sequence:
1. `000_initial_schema` — creates all 6 tables
2. `001_add_tour_tracking` — adds `has_seen_turnusliste_tour` column to `users`

## Existing Deployment (Already Has Tables)

If your database was created before Alembic was introduced, you need to **stamp** it so Alembic knows the schema is already up to date:

```bash
alembic stamp 001_add_tour_tracking
```

This writes `001_add_tour_tracking` into the `alembic_version` table without running any SQL. Future migrations will apply normally after this.

> **When to stamp:** If `alembic current` shows nothing (no `alembic_version` table) but your database already has all tables including the `has_seen_turnusliste_tour` column.

## Prerequisites

Environment variables must be set (via `.env` or shell) for your target database:

- **SQLite (local dev):** `DB_TYPE=sqlite` (default)
- **MySQL (production):** `DB_TYPE=mysql`, `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`

## After Changing Models

When you add, remove, or modify columns/tables in `app/models.py`:

### 1. Generate a Migration

```bash
alembic revision --autogenerate -m "short description of change"
```

This compares your SQLAlchemy models against the current database and creates a new file in `migrations/versions/`.

> **Always review the generated file.** Autogenerate does not detect column renames, some constraint changes, or data migrations. Edit the file manually if needed.

### 2. Review the Migration File

Open the newly created file in `migrations/versions/` and verify:

- The `upgrade()` function correctly describes the intended changes
- The `downgrade()` function properly reverses them
- `down_revision` points to the previous migration

### 3. Test Locally

```bash
alembic upgrade head
```

Run your application and verify everything works as expected.

### 4. Deploy to Production

1. Push your code (including the new migration file) to the production server
2. On the production server, run:

```bash
alembic upgrade head
```

Alembic checks the `alembic_version` table to determine which migrations have been applied, then runs only the new ones.

## Rolling Back

If a migration causes issues in production:

```bash
alembic downgrade -1
```

This runs the `downgrade()` function of the most recently applied migration. Target a specific revision with:

```bash
alembic downgrade <revision_id>
```

## How It Works

- `alembic.ini` defines the migration directory (`migrations/`)
- `migrations/env.py` reads database credentials from environment variables via `config.get_database_uri()` and loads your models so Alembic can compare them against the live schema
- Migration files in `migrations/versions/` form a linked list via `revision` and `down_revision` fields
- The `alembic_version` table in the database stores which revision is currently applied

## Migration History

| Revision | Description |
|---|---|
| `000_initial_schema` | Creates all 6 tables (users, authorized_emails, email_verification_tokens, turnus_sets, favorites, shifts) |
| `001_add_tour_tracking` | Adds `has_seen_turnusliste_tour` column to users table |

## Tests

Tests use `Base.metadata.create_all()` directly on an in-memory SQLite database — they don't go through Alembic. This is intentional: test databases are ephemeral and don't need migration tracking.
