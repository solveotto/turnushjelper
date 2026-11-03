"""scripts/check_db.py is what a host compares before and after a deploy, so it
has to show a migration that didn't run, and still work before it has run."""

import importlib.util
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "check_db.py")


def run_check_db(monkeypatch, capsys, *, with_plan_table):
    engine = create_engine("sqlite:///:memory:")
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if with_plan_table or table.name != "redusert_stilling"
    ]
    Base.metadata.create_all(bind=engine, tables=tables)

    spec = importlib.util.spec_from_file_location("check_db", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_db_session", sessionmaker(bind=engine))

    module.check_database()
    return capsys.readouterr().out


@pytest.mark.parametrize(
    "line",
    ["Favorites: 0", "Shifts: 0", "Søknadsskjema choices: 0", "Placements: 0", "Reduced-position plans: 0"],
)
def test_prints_every_count_after_the_migration(monkeypatch, capsys, line):
    assert line in run_check_db(monkeypatch, capsys, with_plan_table=True)


def test_says_so_when_the_migration_has_not_run(monkeypatch, capsys):
    output = run_check_db(monkeypatch, capsys, with_plan_table=False)
    assert "Reduced-position plans: table missing" in output
    assert "alembic upgrade head" in output


@pytest.mark.parametrize("line", ["Favorites: 0", "Søknadsskjema choices: 0", "Placements: 0"])
def test_still_gives_the_baseline_counts_before_the_migration(monkeypatch, capsys, line):
    assert line in run_check_db(monkeypatch, capsys, with_plan_table=False)
