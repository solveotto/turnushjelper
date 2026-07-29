"""Guards on the turnus-set delete button.

Deleting a turnus set removes every user's favorites and søknadsskjema choices
for that set — a far larger blast radius than deleting a single user, which is
guarded much more heavily. Two guards are tested here:

  * the impact counts shown in the confirm dialog, so the admin sees how much
    data is about to go;
  * a server-side typed confirmation of the year identifier, so a stray click
    (or a forged POST that skips the browser prompt) cannot delete anything.
"""

from app.models import DBUser, Favorites, SoknadsskjemaChoice, TurnusSet
from app.services import turnus_service
from tests.conftest import login_user


def _seed_set_with_user_data(db_session, year="R26", n_users=3):
    ts = TurnusSet(name=year, year_identifier=year, is_active=0)
    db_session.add(ts)
    db_session.commit()

    for i in range(n_users):
        u = DBUser(username=f"bruker_{year}_{i}", password="x", is_auth=0)
        db_session.add(u)
        db_session.commit()
        db_session.add(Favorites(
            user_id=u.id, shift_title=f"OSL_{i}",
            turnus_set_id=ts.id, order_index=0,
        ))
        db_session.add(SoknadsskjemaChoice(
            user_id=u.id, turnus_set_id=ts.id, shift_title=f"OSL_{i}",
        ))
    db_session.commit()
    return ts


class TestDeletionImpact:
    def test_counts_favorites_and_distinct_users(self, patch_db, db_session):
        ts = _seed_set_with_user_data(db_session, n_users=3)

        impact = turnus_service.get_turnus_set_deletion_impact(ts.id)

        assert impact["favorites"] == 3
        assert impact["users"] == 3
        assert impact["soknadsskjema"] == 3

    def test_two_favorites_one_user_counts_one_user(self, patch_db, db_session):
        ts = _seed_set_with_user_data(db_session, n_users=1)
        u = db_session.query(DBUser).filter_by(username="bruker_R26_0").first()
        db_session.add(Favorites(
            user_id=u.id, shift_title="OSL_extra",
            turnus_set_id=ts.id, order_index=1,
        ))
        db_session.commit()

        impact = turnus_service.get_turnus_set_deletion_impact(ts.id)

        assert impact["favorites"] == 2
        assert impact["users"] == 1

    def test_other_sets_are_not_counted(self, patch_db, db_session):
        ts = _seed_set_with_user_data(db_session, year="R26", n_users=2)
        _seed_set_with_user_data(db_session, year="R25", n_users=5)

        assert turnus_service.get_turnus_set_deletion_impact(ts.id)["favorites"] == 2

    def test_unknown_set_returns_zeroes(self, patch_db):
        assert turnus_service.get_turnus_set_deletion_impact(99999)["favorites"] == 0


class TestAdminPageRendersImpact:
    def test_counts_are_exposed_on_the_delete_form(
        self, client, admin_user, db_session
    ):
        ts = _seed_set_with_user_data(db_session, n_users=2)
        login_user(client, admin_user["username"], admin_user["password"])

        resp = client.get("/admin/turnus-sets")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert 'data-confirm-delete-set' in html
        assert 'data-favorites="2"' in html
        assert 'data-users="2"' in html
        assert f'data-identifier="{ts.year_identifier}"' in html


class TestTypedConfirmation:
    def test_wrong_identifier_deletes_nothing(self, client, admin_user, db_session):
        ts = _seed_set_with_user_data(db_session)
        login_user(client, admin_user["username"], admin_user["password"])

        resp = client.post(
            f"/admin/delete-turnus-set/{ts.id}",
            data={"confirm_identifier": "R25"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert db_session.query(TurnusSet).filter_by(id=ts.id).first() is not None
        assert db_session.query(Favorites).filter_by(turnus_set_id=ts.id).count() == 3

    def test_missing_identifier_deletes_nothing(self, client, admin_user, db_session):
        """A forged POST that skips the browser prompt must not delete."""
        ts = _seed_set_with_user_data(db_session)
        login_user(client, admin_user["username"], admin_user["password"])

        client.post(f"/admin/delete-turnus-set/{ts.id}", follow_redirects=True)

        assert db_session.query(TurnusSet).filter_by(id=ts.id).first() is not None

    def test_correct_identifier_deletes(self, client, admin_user, db_session):
        ts = _seed_set_with_user_data(db_session)
        login_user(client, admin_user["username"], admin_user["password"])

        client.post(
            f"/admin/delete-turnus-set/{ts.id}",
            data={"confirm_identifier": "R26"},
            follow_redirects=True,
        )

        assert db_session.query(TurnusSet).filter_by(id=ts.id).first() is None
        assert db_session.query(Favorites).filter_by(turnus_set_id=ts.id).count() == 0

    def test_identifier_match_is_case_insensitive_and_trimmed(
        self, client, admin_user, db_session
    ):
        ts = _seed_set_with_user_data(db_session)
        login_user(client, admin_user["username"], admin_user["password"])

        client.post(
            f"/admin/delete-turnus-set/{ts.id}",
            data={"confirm_identifier": "  r26 "},
            follow_redirects=True,
        )

        assert db_session.query(TurnusSet).filter_by(id=ts.id).first() is None
