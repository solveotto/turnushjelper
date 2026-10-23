"""What a re-import of the *same* turnus set does to users' favorites.

``refresh_turnus_set_shifts`` is the one ingestion path that keeps user data:
it matches old shift titles to new ones (by prefix, else by a tur number unique
on both sides) and rewrites the title in ``Shifts``, ``Favorites``,
``SoknadsskjemaChoice`` and ``Innplassering``. Everything else about a new set
(create, activate) leaves the old rows alone and starts empty.

Two behaviours are pinned here, one good and one sharp:

  * a renamed shift carries its favorites across;
  * a *removed* shift does not — the ``Shifts`` row goes and the ``Favorites``
    row stays behind pointing at a title that no longer exists. Such a row is
    invisible in every view (the templates only render names present in the
    schedule JSON) but still counts toward ``get_max_ordered_index``. The
    detection query is in ``test_removed_shift_leaves_an_orphaned_favorite``.

A fake year identifier is used throughout: nothing here touches the data store,
but a real one invites a future edit to reach the committed turnusdata files.
"""

import json

import pytest

from app.models import (
    DBUser,
    Favorites,
    Innplassering,
    Shifts,
    SoknadsskjemaChoice,
    TurnusSet,
)
from app.services import turnus_service
from app.services.favorites_service import get_max_ordered_index

FAKE_YEAR = "T99"


@pytest.fixture()
def turnus_set(db_session):
    ts = TurnusSet(name=FAKE_YEAR, year_identifier=FAKE_YEAR, is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def user(db_session):
    u = DBUser(username="refreshbruker", password="x", is_auth=0)
    db_session.add(u)
    db_session.commit()
    return u


def seed_shifts(db_session, turnus_set_id, titles):
    for title in titles:
        db_session.add(Shifts(title=title, turnus_set_id=turnus_set_id))
    db_session.commit()


def seed_favorites(db_session, user_id, turnus_set_id, titles):
    for i, title in enumerate(titles):
        db_session.add(
            Favorites(
                user_id=user_id,
                shift_title=title,
                turnus_set_id=turnus_set_id,
                order_index=i,
            )
        )
    db_session.commit()


def write_schedule(tmp_path, titles):
    """A schedule JSON with only the names filled in — refresh reads keys only."""
    path = tmp_path / f"turnus_schedule_{FAKE_YEAR}.json"
    path.write_text(json.dumps([{title: {}} for title in titles]), encoding="utf-8")
    return str(path)


def favorite_titles(db_session, user_id, turnus_set_id):
    db_session.expire_all()
    return sorted(
        f.shift_title
        for f in db_session.query(Favorites)
        .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
        .all()
    )


def shift_titles(db_session, turnus_set_id):
    db_session.expire_all()
    return sorted(
        s.title for s in db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id)
    )


class TestRefreshPreservesFavorites:
    def test_unchanged_shift_keeps_its_favorite(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_01", "OSL_02"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01", "OSL_02"])
        )

        assert summary["unchanged"] == ["OSL_01", "OSL_02"]
        assert favorite_titles(db_session, user.id, turnus_set.id) == ["OSL_01"]

    def test_renamed_shift_carries_its_favorite_over(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        """The prefix match is the whole point of refresh over create."""
        seed_shifts(db_session, turnus_set.id, ["OSL_01", "OSL_02"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01_A", "OSL_02"])
        )

        assert summary["renamed"] == [{"old": "OSL_01", "new": "OSL_01_A"}]
        assert favorite_titles(db_session, user.id, turnus_set.id) == ["OSL_01_A"]
        assert shift_titles(db_session, turnus_set.id) == ["OSL_01_A", "OSL_02"]

    def test_added_shift_creates_no_favorite(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_01"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01", "OSL_99"])
        )

        assert summary["added"] == ["OSL_99"]
        assert favorite_titles(db_session, user.id, turnus_set.id) == ["OSL_01"]

    def test_two_old_names_cannot_collide_on_one_new_name(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        """Both old names prefix-match the single new one.

        Renaming both would violate the unique constraint on
        (user_id, shift_title, turnus_set_id) and abort the whole refresh, so
        the new title is claimed by exactly one of them.
        """
        seed_shifts(db_session, turnus_set.id, ["OSL_0", "OSL_01"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_0", "OSL_01"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01_A"])
        )

        assert len(summary["renamed"]) == 1
        assert shift_titles(db_session, turnus_set.id) == ["OSL_01_A"]

    def test_favorites_in_another_set_are_untouched(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        other = TurnusSet(name="T98", year_identifier="T98", is_active=0)
        db_session.add(other)
        db_session.commit()
        seed_shifts(db_session, turnus_set.id, ["OSL_01"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01"])
        seed_favorites(db_session, user.id, other.id, ["OSL_01"])

        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01_A"])
        )

        assert favorite_titles(db_session, user.id, turnus_set.id) == ["OSL_01_A"]
        assert favorite_titles(db_session, user.id, other.id) == ["OSL_01"]


class TestRemovedShiftOrphansFavorites:
    def test_removed_shift_leaves_an_orphaned_favorite(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        """Current behaviour, pinned so a future change is a deliberate one.

        The Shifts row goes; the Favorites row survives with a dead title. The
        query below is the detector — run it after every refresh:

            SELECT f.id, f.user_id, f.shift_title
              FROM favorites f
              LEFT JOIN shifts s
                ON s.title = f.shift_title
               AND s.turnus_set_id = f.turnus_set_id
             WHERE f.turnus_set_id = :id AND s.id IS NULL;
        """
        seed_shifts(db_session, turnus_set.id, ["OSL_01", "GONE_02"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01", "GONE_02"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01"])
        )

        assert summary["removed"] == ["GONE_02"]
        assert shift_titles(db_session, turnus_set.id) == ["OSL_01"]
        # The favorite is still there, pointing at nothing.
        assert favorite_titles(db_session, user.id, turnus_set.id) == [
            "GONE_02",
            "OSL_01",
        ]

        orphans = (
            db_session.query(Favorites)
            .outerjoin(
                Shifts,
                (Shifts.title == Favorites.shift_title)
                & (Shifts.turnus_set_id == Favorites.turnus_set_id),
            )
            .filter(Favorites.turnus_set_id == turnus_set.id, Shifts.id.is_(None))
            .all()
        )
        assert [o.shift_title for o in orphans] == ["GONE_02"]

    def test_orphan_still_counts_toward_the_next_position(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        """Why the orphan matters: it silently reserves a position number."""
        seed_shifts(db_session, turnus_set.id, ["OSL_01", "GONE_02"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_01", "GONE_02"])

        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01"])
        )

        assert get_max_ordered_index(user.id, turnus_set.id) == 1


def seed_choices(db_session, user_id, turnus_set_id, titles):
    for title in titles:
        db_session.add(
            SoknadsskjemaChoice(
                user_id=user_id, turnus_set_id=turnus_set_id, shift_title=title, linje_135=1
            )
        )
    db_session.commit()


def seed_innplassering(db_session, turnus_set_id, titles):
    for i, title in enumerate(titles):
        db_session.add(
            Innplassering(
                turnus_set_id=turnus_set_id,
                rullenummer=f"9{i:04d}",
                shift_title=title,
                linjenummer=1,
            )
        )
    db_session.commit()


def choice_titles(db_session, turnus_set_id):
    db_session.expire_all()
    return sorted(
        c.shift_title
        for c in db_session.query(SoknadsskjemaChoice).filter_by(turnus_set_id=turnus_set_id)
    )


def innplassering_titles(db_session, turnus_set_id):
    db_session.expire_all()
    return sorted(
        r.shift_title
        for r in db_session.query(Innplassering).filter_by(turnus_set_id=turnus_set_id)
    )


class TestRenameByTurNumber:
    """R27: the Timeskjema was hand-fixed from OSL_17_ALTSOM to OSL_17_ALSTOM.
    Neither title is a prefix of the other, so without the number match the
    refresh deleted and re-added the shift and every favorite on it vanished."""

    def test_misspelled_suffix_renamed_by_tur_number(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_16_ALSTOM", "OSL_17_ALTSOM"])
        seed_favorites(db_session, user.id, turnus_set.id, ["OSL_16_ALSTOM", "OSL_17_ALTSOM"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_16_ALSTOM", "OSL_17_ALSTOM"])
        )

        assert summary["renamed"] == [{"old": "OSL_17_ALTSOM", "new": "OSL_17_ALSTOM"}]
        assert summary["removed"] == []
        assert summary["added"] == []
        assert shift_titles(db_session, turnus_set.id) == ["OSL_16_ALSTOM", "OSL_17_ALSTOM"]
        db_session.expire_all()
        renamed = (
            db_session.query(Favorites)
            .filter_by(user_id=user.id, turnus_set_id=turnus_set.id, shift_title="OSL_17_ALSTOM")
            .one()
        )
        assert renamed.order_index == 1

    def test_ambiguous_old_number_is_remove_and_add(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_17_A", "OSL_17_B"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_17_C"])
        )

        assert summary["renamed"] == []
        assert summary["removed"] == ["OSL_17_A", "OSL_17_B"]
        assert summary["added"] == ["OSL_17_C"]

    def test_ambiguous_new_number_is_remove_and_add(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_17_A"])

        summary = turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_17_B", "OSL_17_C"])
        )

        assert summary["renamed"] == []
        assert summary["removed"] == ["OSL_17_A"]
        assert summary["added"] == ["OSL_17_B", "OSL_17_C"]


class TestRenameCarriesAllUserData:
    def test_number_rename_carries_choices_and_innplassering(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_17_ALTSOM"])
        seed_choices(db_session, user.id, turnus_set.id, ["OSL_17_ALTSOM"])
        seed_innplassering(db_session, turnus_set.id, ["OSL_17_ALTSOM", "OSL_17_ALTSOM"])

        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_17_ALSTOM"])
        )

        assert choice_titles(db_session, turnus_set.id) == ["OSL_17_ALSTOM"]
        assert innplassering_titles(db_session, turnus_set.id) == [
            "OSL_17_ALSTOM",
            "OSL_17_ALSTOM",
        ]

    def test_prefix_rename_carries_choices_and_innplassering(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        seed_shifts(db_session, turnus_set.id, ["OSL_01"])
        seed_choices(db_session, user.id, turnus_set.id, ["OSL_01"])
        seed_innplassering(db_session, turnus_set.id, ["OSL_01"])

        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_01_A"])
        )

        assert choice_titles(db_session, turnus_set.id) == ["OSL_01_A"]
        assert innplassering_titles(db_session, turnus_set.id) == ["OSL_01_A"]

    def test_rows_in_another_set_are_untouched(
        self, patch_db, db_session, tmp_path, turnus_set, user
    ):
        other = TurnusSet(name="T98", year_identifier="T98", is_active=0)
        db_session.add(other)
        db_session.commit()
        seed_shifts(db_session, turnus_set.id, ["OSL_17_ALTSOM"])
        seed_choices(db_session, user.id, other.id, ["OSL_17_ALTSOM"])
        seed_innplassering(db_session, other.id, ["OSL_17_ALTSOM"])

        turnus_service.refresh_turnus_set_shifts(
            turnus_set.id, write_schedule(tmp_path, ["OSL_17_ALSTOM"])
        )

        assert choice_titles(db_session, other.id) == ["OSL_17_ALTSOM"]
        assert innplassering_titles(db_session, other.id) == ["OSL_17_ALTSOM"]
