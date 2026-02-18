# Database Migrations with Alembic

This project uses [Alembic](https://alembic.sqlalchemy.org/) to manage database schema changes. Alembic tracks migrations as a chain of revision files in `migrations/versions/`.

## Prerequisites

- Environment variables must be set (via `.env` or shell) for your target database:
  - **SQLite (local dev):** `DB_TYPE=sqlite` (default)
  - **MySQL (production):** `DB_TYPE=mysql`, `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`

## After Changing Models

Whenever you add, remove, or modify columns/tables in `app/models.py`, follow these steps:

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

Alembic checks the `alembic_version` table in the database to determine which migrations have already been applied, then runs only the new ones.

## Useful Commands

| Command | Description |
|---|---|
| `alembic current` | Show the revision currently applied to the database |
| `alembic history` | List all migration revisions in order |
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Roll back the most recent migration |
| `alembic upgrade head --sql` | Print the SQL that would run (dry run, no changes made) |

## Rolling Back

If a migration causes issues in production:

```bash
alembic downgrade -1
```

This runs the `downgrade()` function of the most recently applied migration. You can repeat this to roll back further, or target a specific revision:

```bash
alembic downgrade <revision_id>
```

## How It Works

- `alembic.ini` defines the migration directory (`migrations/`)
- `migrations/env.py` reads database credentials from environment variables via `config.get_database_uri()` and loads your models so Alembic can compare them against the live schema
- Migration files in `migrations/versions/` form a linked list via `revision` and `down_revision` fields
- The `alembic_version` table in the database stores which revision is currently applied
