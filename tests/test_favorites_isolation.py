"""Favorites belong to one user and one turnus set — and stay there.

The favorites table is the app's only substantial user-generated state, and it
is keyed on ``(user_id, shift_title, turnus_set_id)``. Two ways that keying can
leak are covered here:

  * **across users** — one account reordering or reading another's list;
  * **across turnus sets** — a new rutetermin is activated once or twice a
    year, and the old set's favorites must neither disappear nor bleed into the
    new one.

Activation itself is asserted to be a no-op on the table: it only flips
``TurnusSet.is_active``, and every user simply starts empty in the new set and
re-populates it through /import-favorites.
"""

import pytest

from app.models import DBUser, Favorites, TurnusSet
from app.services import favorites_service, turnus_service
from app.services.user_service import hash_password
from tests.conftest import login_user

OLD_YEAR = "T98"
NEW_YEAR = "T99"


@pytest.fixture()
def two_sets(db_session):
    """An active 'old' set and an inactive 'new' one, as before a cutover."""
    old = TurnusSet(name=OLD_YEAR, year_identifier=OLD_YEAR, is_active=1)
    new = TurnusSet(name=NEW_YEAR, year_identifier=NEW_YEAR, is_active=0)
    db_session.add_all([old, new])
    db_session.commit()
    return old, new


def make_user(db_session, username):
    user = DBUser(
        username=username,
        email=f"{username}@example.com",
        password=hash_password("password123"),
        is_auth=0,
        email_verified=1,
    )
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": username, "password": "password123"}


def add_favorites(db_session, user_id, turnus_set_id, titles):
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


def order_of(db_session, user_id, turnus_set_id):
    db_session.expire_all()
    rows = (
        db_session.query(Favorites)
        .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
        .order_by(Favorites.order_index)
        .all()
    )
    return [r.shift_title for r in rows]


class TestAcrossUsers:
    def test_one_user_cannot_reorder_anothers_favorites(
        self, client, sample_user, db_session, two_sets
    ):
        old, _ = two_sets
        other = make_user(db_session, "annenbruker")
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B"])
        add_favorites(db_session, other["id"], old.id, ["X", "Y", "Z"])

        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.post(
            "/api/move-favorite", json={"shift_title": "Z", "direction": "up"}
        )

        assert resp.get_json()["status"] == "error"
        assert order_of(db_session, other["id"], old.id) == ["X", "Y", "Z"]
        assert order_of(db_session, sample_user["id"], old.id) == ["A", "B"]

    def test_one_user_cannot_set_position_on_anothers_favorite(
        self, client, sample_user, db_session, two_sets
    ):
        old, _ = two_sets
        other = make_user(db_session, "annenbruker")
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B"])
        add_favorites(db_session, other["id"], old.id, ["X", "Y", "Z"])

        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.post(
            "/api/set-favorite-position",
            json={"shift_title": "Z", "new_position": 1},
        )

        assert resp.get_json()["status"] == "error"
        assert order_of(db_session, other["id"], old.id) == ["X", "Y", "Z"]

    def test_a_reorder_leaves_other_users_untouched(
        self, client, sample_user, db_session, two_sets
    ):
        """Same shift titles for both users — the renumbering is per user."""
        old, _ = two_sets
        other = make_user(db_session, "annenbruker")
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B", "C"])
        add_favorites(db_session, other["id"], old.id, ["A", "B", "C"])

        login_user(client, sample_user["username"], sample_user["password"])
        client.post("/api/move-favorite", json={"shift_title": "C", "direction": "up"})

        assert order_of(db_session, sample_user["id"], old.id) == ["A", "C", "B"]
        assert order_of(db_session, other["id"], old.id) == ["A", "B", "C"]

    def test_service_lookup_is_per_user(self, patch_db, db_session, two_sets):
        old, _ = two_sets
        user_a = make_user(db_session, "bruker_a")
        user_b = make_user(db_session, "bruker_b")
        add_favorites(db_session, user_a["id"], old.id, ["A"])
        add_favorites(db_session, user_b["id"], old.id, ["B"])

        assert favorites_service.get_favorite_lst(user_a["id"], old.id) == ["A"]
        assert favorites_service.get_favorite_lst(user_b["id"], old.id) == ["B"]


class TestAcrossTurnusSets:
    def test_favorites_are_scoped_to_their_set(
        self, patch_db, db_session, sample_user, two_sets
    ):
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B"])
        add_favorites(db_session, sample_user["id"], new.id, ["C"])

        assert favorites_service.get_favorite_lst(sample_user["id"], old.id) == [
            "A",
            "B",
        ]
        assert favorites_service.get_favorite_lst(sample_user["id"], new.id) == ["C"]

    def test_reorder_only_touches_the_selected_set(
        self, client, sample_user, db_session, two_sets
    ):
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B", "C"])
        add_favorites(db_session, sample_user["id"], new.id, ["A", "B", "C"])

        login_user(client, sample_user["username"], sample_user["password"])
        client.post("/api/move-favorite", json={"shift_title": "C", "direction": "up"})

        assert order_of(db_session, sample_user["id"], old.id) == ["A", "C", "B"]
        assert order_of(db_session, sample_user["id"], new.id) == ["A", "B", "C"]

    def test_switch_year_moves_the_reorder_to_the_other_set(
        self, client, sample_user, db_session, two_sets
    ):
        """The year switcher stores a session choice; reorders must follow it.

        This is the pre-cutover case: the old set is still active while the
        admin and testers browse the new one.
        """
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B", "C"])
        add_favorites(db_session, sample_user["id"], new.id, ["A", "B", "C"])

        login_user(client, sample_user["username"], sample_user["password"])
        client.get(f"/switch-year/{new.id}", follow_redirects=True)
        client.post("/api/move-favorite", json={"shift_title": "C", "direction": "up"})

        assert order_of(db_session, sample_user["id"], new.id) == ["A", "C", "B"]
        assert order_of(db_session, sample_user["id"], old.id) == ["A", "B", "C"]

    def test_toggle_writes_into_the_selected_set_only(
        self, client, sample_user, db_session, two_sets
    ):
        old, new = two_sets

        login_user(client, sample_user["username"], sample_user["password"])
        client.get(f"/switch-year/{new.id}", follow_redirects=True)
        resp = client.post(
            "/api/toggle_favorite", json={"shift_title": "OSL_01", "favorite": True}
        )

        assert resp.get_json()["status"] == "success"
        assert order_of(db_session, sample_user["id"], new.id) == ["OSL_01"]
        assert order_of(db_session, sample_user["id"], old.id) == []


class TestActivation:
    def test_activation_does_not_touch_any_favorite(
        self, patch_db, db_session, sample_user, two_sets
    ):
        """Activating a set must never migrate, clear or renumber favorites."""
        old, new = two_sets
        other = make_user(db_session, "annenbruker")
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B", "C"])
        add_favorites(db_session, other["id"], old.id, ["X"])

        before = sorted(
            (f.user_id, f.shift_title, f.turnus_set_id, f.order_index)
            for f in db_session.query(Favorites).all()
        )

        ok, _ = turnus_service.set_active_turnus_set(new.id)
        assert ok

        db_session.expire_all()
        after = sorted(
            (f.user_id, f.shift_title, f.turnus_set_id, f.order_index)
            for f in db_session.query(Favorites).all()
        )
        assert after == before

    def test_new_set_starts_empty_while_the_old_one_keeps_its_favorites(
        self, patch_db, db_session, sample_user, two_sets
    ):
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B"])

        turnus_service.set_active_turnus_set(new.id)

        # Active set (no explicit id) resolves to the new, empty one …
        assert favorites_service.get_favorite_lst(sample_user["id"]) == []
        # … while the old set is still reachable with its list intact.
        assert favorites_service.get_favorite_lst(sample_user["id"], old.id) == [
            "A",
            "B",
        ]

    def test_import_source_is_offered_after_a_cutover(
        self, patch_db, db_session, sample_user, two_sets
    ):
        """What /import-favorites keys off: favorites exist in some other set."""
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B"])

        turnus_service.set_active_turnus_set(new.id)

        assert favorites_service.user_has_favorites_in_other_sets(
            sample_user["id"], new.id
        )

    def test_new_favorites_start_at_index_one_in_the_new_set(
        self, patch_db, db_session, sample_user, two_sets
    ):
        """A high order_index in the old set must not offset the new set."""
        old, new = two_sets
        add_favorites(db_session, sample_user["id"], old.id, ["A", "B", "C"])
        db_session.query(Favorites).filter_by(
            shift_title="C", turnus_set_id=old.id
        ).update({"order_index": 99})
        db_session.commit()

        turnus_service.set_active_turnus_set(new.id)

        assert favorites_service.get_max_ordered_index(sample_user["id"]) == 0
