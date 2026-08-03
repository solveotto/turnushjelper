"""Coverage for the two favorite-reordering endpoints.

``/api/move-favorite`` and ``/api/set-favorite-position`` were the only
favorites endpoints with no tests at all, and reordering is the part of the
feature a user notices immediately when it breaks.

Both endpoints rebuild the entire ``order_index`` sequence instead of swapping
two values. That is deliberate: legacy rows can share an index, and a raw swap
is then a silent no-op. The renumbering is what these tests pin.
"""

import pytest

from app.models import Favorites, TurnusSet
from tests.conftest import login_user


@pytest.fixture()
def active_set(db_session):
    ts = TurnusSet(name="T99", year_identifier="T99", is_active=1)
    db_session.add(ts)
    db_session.commit()
    return ts


@pytest.fixture()
def logged_in(client, sample_user):
    login_user(client, sample_user["username"], sample_user["password"])
    return client


def seed_favorites(db_session, user_id, turnus_set_id, titles, indices=None):
    """Insert favorites in list order. ``indices`` defaults to 0..n-1."""
    if indices is None:
        indices = range(len(titles))
    for title, idx in zip(titles, indices):
        db_session.add(
            Favorites(
                user_id=user_id,
                shift_title=title,
                turnus_set_id=turnus_set_id,
                order_index=idx,
            )
        )
    db_session.commit()


def current_order(db_session, user_id, turnus_set_id):
    """Titles in stored order — what the '#N' pills are numbered from."""
    db_session.expire_all()
    rows = (
        db_session.query(Favorites)
        .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
        .order_by(Favorites.order_index)
        .all()
    )
    return [r.shift_title for r in rows]


def stored_indices(db_session, user_id, turnus_set_id):
    db_session.expire_all()
    rows = (
        db_session.query(Favorites)
        .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
        .order_by(Favorites.order_index)
        .all()
    )
    return [r.order_index for r in rows]


def move(client, title, direction):
    return client.post(
        "/api/move-favorite",
        json={"shift_title": title, "direction": direction},
    )


def set_position(client, title, position):
    return client.post(
        "/api/set-favorite-position",
        json={"shift_title": title, "new_position": position},
    )


class TestMoveFavorite:
    def test_move_up_swaps_with_predecessor(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        resp = move(logged_in, "B", "up")

        assert resp.get_json()["status"] == "success"
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "B",
            "A",
            "C",
        ]

    def test_move_down_swaps_with_successor(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        resp = move(logged_in, "B", "down")

        assert resp.get_json()["status"] == "success"
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "A",
            "C",
            "B",
        ]

    def test_move_up_at_top_is_refused(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = move(logged_in, "A", "up")

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    def test_move_down_at_bottom_is_refused(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = move(logged_in, "B", "down")

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    def test_indices_stay_contiguous_from_zero(
        self, logged_in, sample_user, db_session, active_set
    ):
        """Gaps in order_index are what make the '#N' pills skip numbers."""
        seed_favorites(
            db_session,
            sample_user["id"],
            active_set.id,
            ["A", "B", "C", "D"],
            indices=[0, 5, 10, 40],
        )

        move(logged_in, "D", "up")

        assert stored_indices(db_session, sample_user["id"], active_set.id) == [
            0,
            1,
            2,
            3,
        ]
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "A",
            "B",
            "D",
            "C",
        ]

    def test_legacy_duplicate_indices_are_repaired(
        self, logged_in, sample_user, db_session, active_set
    ):
        """Rows sharing an index: a raw index swap would be a no-op here."""
        seed_favorites(
            db_session,
            sample_user["id"],
            active_set.id,
            ["A", "B", "C"],
            indices=[0, 0, 0],
        )

        resp = move(logged_in, "C", "up")

        assert resp.get_json()["status"] == "success"
        assert stored_indices(db_session, sample_user["id"], active_set.id) == [0, 1, 2]
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "A",
            "C",
            "B",
        ]

    @pytest.mark.parametrize("direction", ["sideways", "", None])
    def test_invalid_direction_is_rejected(
        self, logged_in, sample_user, db_session, active_set, direction
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = move(logged_in, "A", direction)

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    def test_unknown_shift_title_changes_nothing(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = move(logged_in, "DOES_NOT_EXIST", "up")

        assert resp.get_json()["status"] == "error"
        assert stored_indices(db_session, sample_user["id"], active_set.id) == [0, 1]

    def test_requires_login(self, client):
        assert client.post(
            "/api/move-favorite", json={"shift_title": "A", "direction": "up"}
        ).status_code == 302

    def test_no_active_turnus_set_is_an_error(self, logged_in, sample_user):
        """No set seeded at all — the endpoint must not guess one."""
        resp = move(logged_in, "A", "up")

        assert resp.get_json()["status"] == "error"


class TestSetFavoritePosition:
    def test_move_to_front(self, logged_in, sample_user, db_session, active_set):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        resp = set_position(logged_in, "C", 1)

        assert resp.get_json()["status"] == "success"
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "C",
            "A",
            "B",
        ]

    def test_move_to_end(self, logged_in, sample_user, db_session, active_set):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        set_position(logged_in, "A", 3)

        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "B",
            "C",
            "A",
        ]

    def test_position_beyond_the_end_clamps(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        resp = set_position(logged_in, "A", 99)

        assert resp.get_json()["status"] == "success"
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "B",
            "C",
            "A",
        ]
        assert stored_indices(db_session, sample_user["id"], active_set.id) == [0, 1, 2]

    @pytest.mark.parametrize("position", [0, -3])
    def test_position_below_one_is_rejected(
        self, logged_in, sample_user, db_session, active_set, position
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = set_position(logged_in, "B", position)

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    @pytest.mark.parametrize("position", ["førsteplass", "", None])
    def test_non_numeric_position_is_rejected(
        self, logged_in, sample_user, db_session, active_set, position
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = set_position(logged_in, "B", position)

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    def test_same_position_is_a_noop(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(
            db_session, sample_user["id"], active_set.id, ["A", "B", "C"]
        )

        resp = set_position(logged_in, "B", 2)

        assert resp.get_json()["status"] == "success"
        assert current_order(db_session, sample_user["id"], active_set.id) == [
            "A",
            "B",
            "C",
        ]

    def test_unknown_shift_title_changes_nothing(
        self, logged_in, sample_user, db_session, active_set
    ):
        seed_favorites(db_session, sample_user["id"], active_set.id, ["A", "B"])

        resp = set_position(logged_in, "DOES_NOT_EXIST", 1)

        assert resp.get_json()["status"] == "error"
        assert current_order(db_session, sample_user["id"], active_set.id) == ["A", "B"]

    def test_requires_login(self, client):
        assert client.post(
            "/api/set-favorite-position",
            json={"shift_title": "A", "new_position": 1},
        ).status_code == 302
