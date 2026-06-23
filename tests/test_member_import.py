"""Tests for the NLF member list import (parser + sync service)."""

import pytest
from openpyxl import Workbook

from app.models import DBUser
from app.services import user_service
from app.services.user_service import hash_password
from app.utils.member_excel import parse_member_excel


def make_xlsx(path, rows, header=("Navn", "Medlemsnr")):
    wb = Workbook()
    ws = wb.active
    if header:
        ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return str(path)


def add_user(db_session, username, name=None, medlemsnummer=None,
             rullenummer=None, is_stub=0, email=None, **kwargs):
    user = DBUser(
        username=username,
        password=hash_password("pw"),
        name=name,
        medlemsnummer=medlemsnummer,
        rullenummer=rullenummer,
        is_stub=is_stub,
        email=email,
        **kwargs,
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestParseMemberExcel:
    def test_parses_rows(self, tmp_path):
        path = make_xlsx(tmp_path / "m.xlsx", [
            ("Nordmann, Ola", 60010),
            ("Hansen, Kari", 60011),
        ])
        members = parse_member_excel(path)
        assert members[0]["name"] == "Nordmann, Ola"
        assert members[0]["medlemsnummer"] == "60010"
        assert members[0]["ans_dato"] is None
        assert members[0]["fodt_dato"] is None
        assert members[0]["stasjoneringssted"] is None
        assert len(members) == 2

    def test_int_and_float_medlemsnr_to_str(self, tmp_path):
        path = make_xlsx(tmp_path / "m.xlsx", [("A, B", 60010.0)])
        members = parse_member_excel(path)
        assert members[0]["medlemsnummer"] == "60010"

    def test_missing_header_raises(self, tmp_path):
        path = make_xlsx(
            tmp_path / "m.xlsx", [("Nordmann, Ola", 60010)],
            header=("Name", "Number"),
        )
        with pytest.raises(ValueError, match="Navn"):
            parse_member_excel(path)

    def test_header_case_insensitive(self, tmp_path):
        path = make_xlsx(
            tmp_path / "m.xlsx", [("A, B", 1)], header=("NAVN", "medlemsnr"),
        )
        assert len(parse_member_excel(path)) == 1

    def test_skips_fully_empty_rows(self, tmp_path):
        path = make_xlsx(tmp_path / "m.xlsx", [
            ("A, B", 60010),
            (None, None),
            ("C, D", 60011),
        ])
        assert len(parse_member_excel(path)) == 2


class TestSyncMembersFromExcel:
    def test_match_registered_user_by_name(self, patch_db, db_session):
        user = add_user(db_session, "ola", name="Nordmann, Ola",
                        email="ola@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60010"}]
        )
        assert report["matched"] == 1
        db_session.expire_all()
        assert db_session.get(DBUser, user.id).medlemsnummer == "60010"

    def test_match_is_case_and_whitespace_insensitive(self, patch_db, db_session):
        user = add_user(db_session, "ola", name="Nordmann, Ola",
                        email="ola@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "  NORDMANN ,  ola ", "medlemsnummer": "60010"}]
        )
        assert report["matched"] == 1
        db_session.expire_all()
        assert db_session.get(DBUser, user.id).medlemsnummer == "60010"

    def test_match_stub_keeps_rullenummer(self, patch_db, db_session):
        stub = add_user(db_session, "__stub_111", name="Hansen, Kari",
                        rullenummer="111", is_stub=1)
        report = user_service.sync_members_from_excel(
            [{"name": "Hansen, Kari", "medlemsnummer": "60011"}]
        )
        assert report["matched"] == 1
        db_session.expire_all()
        updated = db_session.get(DBUser, stub.id)
        assert updated.medlemsnummer == "60011"
        assert updated.rullenummer == "111"

    def test_unmatched_row_creates_stub(self, patch_db, db_session):
        report = user_service.sync_members_from_excel(
            [{"name": "Ny, Person", "medlemsnummer": "60012"}]
        )
        assert report["created"] == 1
        stub = db_session.query(DBUser).filter_by(medlemsnummer="60012").first()
        assert stub.username == "__stub_m60012"
        assert stub.is_stub == 1
        assert stub.name == "Ny, Person"

    def test_registered_user_with_differing_mnr_is_conflict(self, patch_db, db_session):
        user = add_user(db_session, "ola", name="Nordmann, Ola",
                        medlemsnummer="60013", email="ola@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "99999"}]
        )
        assert len(report["conflicts"]) == 1
        db_session.expire_all()
        assert db_session.get(DBUser, user.id).medlemsnummer == "60013"

    def test_mnr_owned_by_other_registered_user_is_conflict(self, patch_db, db_session):
        add_user(db_session, "owner", name="Eier, Per",
                 medlemsnummer="60014", email="eier@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "Annen, Person", "medlemsnummer": "60014"}]
        )
        assert len(report["conflicts"]) == 1
        assert report["created"] == 0

    def test_mnr_on_wrong_stub_is_reassigned(self, patch_db, db_session):
        # NOTE: SQLite reuses freed row ids, so assert on name/count, not id.
        add_user(db_session, "__stub_m60015", name="Feil, Navn",
                 medlemsnummer="60015", is_stub=1)
        report = user_service.sync_members_from_excel(
            [{"name": "Riktig, Navn", "medlemsnummer": "60015"}]
        )
        assert report["deleted_stubs"] >= 1
        assert report["created"] == 1
        db_session.expire_all()
        assert db_session.query(DBUser).filter_by(name="Feil, Navn").count() == 0
        stubs = db_session.query(DBUser).filter_by(medlemsnummer="60015").all()
        assert len(stubs) == 1
        assert stubs[0].name == "Riktig, Navn"

    def test_duplicate_stub_names_deleted_and_recreated(self, patch_db, db_session):
        add_user(db_session, "__stub_1", name="Dobbel, Gjenganger",
                 rullenummer="1", is_stub=1)
        add_user(db_session, "__stub_2", name="Dobbel, Gjenganger",
                 rullenummer="2", is_stub=1)
        report = user_service.sync_members_from_excel(
            [{"name": "Dobbel, Gjenganger", "medlemsnummer": "60016"}]
        )
        assert report["created"] == 1
        db_session.expire_all()
        assert db_session.query(DBUser).filter_by(username="__stub_1").count() == 0
        assert db_session.query(DBUser).filter_by(username="__stub_2").count() == 0
        survivors = db_session.query(DBUser).filter_by(
            name="Dobbel, Gjenganger"
        ).all()
        assert len(survivors) == 1
        assert survivors[0].medlemsnummer == "60016"
        assert survivors[0].username == "__stub_m60016"

    def test_leftover_stub_without_mnr_is_reported_not_deleted(self, patch_db, db_session):
        stale = add_user(db_session, "__stub_999", name="Borte, Vekk",
                         rullenummer="999", is_stub=1)
        stale_id = stale.id
        report = user_service.sync_members_from_excel(
            [{"name": "Ny, Person", "medlemsnummer": "60017"}]
        )
        assert report["deleted_stubs"] == 0
        db_session.expire_all()
        stale_user = db_session.query(DBUser).filter_by(id=stale_id).first()
        assert stale_user is not None
        assert stale_user.not_on_nlf_list == 1
        assert report["flagged"] >= 1

    def test_registered_users_absent_untouched_and_reported(self, patch_db, db_session):
        user = add_user(db_session, "borte", name="Borte, Bruker",
                        email="borte@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "Annen, Person", "medlemsnummer": "60018"}]
        )
        db_session.expire_all()
        db_user = db_session.get(DBUser, user.id)
        assert db_user is not None
        # registered users without member identifiers are not flagged
        assert db_user.not_on_nlf_list in (0, None)

    def test_stale_stub_with_mnr_no_longer_on_list_is_reported_not_deleted(self, patch_db, db_session):
        # Stub from a previous run that has since fallen off the member list
        # (e.g. left NLF) — must not be deleted; persistent flag is set instead.
        stale = add_user(db_session, "__stub_m70099", name="Forlatt, Person",
                         medlemsnummer="70099", is_stub=1)
        stale_id = stale.id
        report = user_service.sync_members_from_excel(
            [{"name": "Ny, Person", "medlemsnummer": "70017"}]
        )
        assert report["deleted_stubs"] == 0
        db_session.expire_all()
        stale_user = db_session.query(DBUser).filter_by(id=stale_id).first()
        assert stale_user is not None
        assert stale_user.not_on_nlf_list == 1
        assert stale_user.medlemsnummer == "70099"

    def test_registered_user_with_stale_mnr_reported_not_on_list(self, patch_db, db_session):
        # A registered user keeping a stale medlemsnummer must NOT be
        # auto-deleted; the persistent flag is set instead.
        user = add_user(db_session, "gammel", name="Gammel, Bruker",
                        medlemsnummer="70100", email="gammel@test.com")
        report = user_service.sync_members_from_excel(
            [{"name": "Annen, Person", "medlemsnummer": "70101"}]
        )
        db_session.expire_all()
        db_user = db_session.get(DBUser, user.id)
        assert db_user is not None
        assert db_user.not_on_nlf_list == 1
        assert db_user.medlemsnummer == "70100"

    def test_duplicate_mnr_in_excel_is_conflict(self, patch_db, db_session):
        report = user_service.sync_members_from_excel([
            {"name": "Første, Person", "medlemsnummer": "60019"},
            {"name": "Andre, Person", "medlemsnummer": "60019"},
        ])
        assert report["created"] == 1
        assert len(report["conflicts"]) == 1

    def test_invalid_rows_skipped(self, patch_db):
        report = user_service.sync_members_from_excel([
            {"name": "", "medlemsnummer": "60020"},
            {"name": "Uten, Nummer", "medlemsnummer": "ikke-tall"},
        ])
        assert report["skipped_invalid"] == 2
        assert report["created"] == 0

    def test_second_run_is_idempotent(self, patch_db, db_session):
        add_user(db_session, "ola", name="Nordmann, Ola", email="ola@test.com")
        members = [
            {"name": "Nordmann, Ola", "medlemsnummer": "60021"},
            {"name": "Ny, Person", "medlemsnummer": "60022"},
        ]
        first = user_service.sync_members_from_excel(members)
        assert first["matched"] == 1
        assert first["created"] == 1

        second = user_service.sync_members_from_excel(members)
        assert second["unchanged"] == 2
        assert second["matched"] == 0
        assert second["created"] == 0
        assert second["deleted_stubs"] == 0
        assert second["conflicts"] == []


class TestMedlemsnummerNormalization:
    def test_leading_zeros_stripped_on_import(self, patch_db, db_session):
        report = user_service.sync_members_from_excel(
            [{"name": "Null, Foran", "medlemsnummer": "068588"}]
        )
        assert report["created"] == 1
        stub = db_session.query(DBUser).filter_by(medlemsnummer="68588").first()
        assert stub is not None
        assert stub.username == "__stub_m68588"

    def test_lookup_matches_with_and_without_leading_zero(self, patch_db, db_session):
        user_service.sync_members_from_excel(
            [{"name": "Null, Foran", "medlemsnummer": "068588"}]
        )
        assert user_service.get_user_by_medlemsnummer("68588") is not None
        assert user_service.get_user_by_medlemsnummer("068588") is not None
        assert user_service.get_user_by_medlemsnummer(68588) is not None

    def test_reimport_with_leading_zero_is_idempotent(self, patch_db, db_session):
        members = [{"name": "Null, Foran", "medlemsnummer": "068588"}]
        user_service.sync_members_from_excel(members)
        second = user_service.sync_members_from_excel(members)
        assert second["unchanged"] == 1
        assert second["created"] == 0


class TestExcelThenPdfMerge:
    """Reproduces the Excel-first-then-PDF import order: the two sources
    must merge into one user with both numbers, in either order."""

    PDF_ROW = {
        "rullenummer": "555", "etternavn": "Nordmann", "fornavn": "Ola",
        "stasjoneringssted": "OSLO", "ans_dato": "01.01.2020",
        "fodt_dato": "02.02.1990", "seniority_nr": 4,
    }

    def test_pdf_sync_merges_into_member_stub_by_name(self, patch_db, db_session):
        user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60050"}]
        )
        result = user_service.sync_employees_from_scrape([self.PDF_ROW])
        assert result["merged_by_name"] == 1
        assert result["skipped_unmatched"] == 0

        users = db_session.query(DBUser).filter_by(name="Nordmann, Ola").all()
        assert len(users) == 1
        assert users[0].medlemsnummer == "60050"
        assert users[0].rullenummer == "555"
        assert users[0].seniority_nr == 4
        assert users[0].stasjoneringssted is None  # PDF sync no longer writes HR fields

    def test_pdf_sync_does_not_merge_ambiguous_names(self, patch_db, db_session):
        # Ambiguous match (two same-name candidates) must not create a new
        # user either — the PDF sync never creates users, it only enriches
        # existing member-list users.
        user_service.sync_members_from_excel([
            {"name": "Nordmann, Ola", "medlemsnummer": "60051"},
        ])
        add_user(db_session, "tvilling", name="Nordmann, Ola",
                 email="tvilling@test.com")
        result = user_service.sync_employees_from_scrape([self.PDF_ROW])
        assert result["merged_by_name"] == 0
        assert result["skipped_unmatched"] == 1
        assert db_session.query(DBUser).filter_by(
            name="Nordmann, Ola"
        ).count() == 2

    def test_excel_reimport_absorbs_pdf_duplicate_stubs(self, patch_db, db_session):
        # The broken state: Excel imported first, then the old PDF sync
        # created a rullenummer twin for the same person.
        user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60052"}]
        )
        add_user(db_session, "__stub_555", name="Nordmann, Ola",
                 rullenummer="555", is_stub=1,
                 stasjoneringssted="OSLO", seniority_nr=4)

        report = user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60052"}]
        )
        assert report["deleted_stubs"] == 1

        users = db_session.query(DBUser).filter_by(name="Nordmann, Ola").all()
        assert len(users) == 1
        assert users[0].medlemsnummer == "60052"
        assert users[0].rullenummer == "555"
        assert users[0].stasjoneringssted == "OSLO"
        assert users[0].seniority_nr == 4

    def test_excel_import_absorbs_twin_into_registered_user(self, patch_db, db_session):
        add_user(db_session, "ola", name="Nordmann, Ola", email="ola@test.com")
        add_user(db_session, "__stub_555", name="Nordmann, Ola",
                 rullenummer="555", is_stub=1, seniority_nr=4)

        report = user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60053"}]
        )
        assert report["matched"] == 1
        assert report["deleted_stubs"] == 1

        users = db_session.query(DBUser).filter_by(name="Nordmann, Ola").all()
        assert len(users) == 1
        assert users[0].username == "ola"
        assert users[0].medlemsnummer == "60053"
        assert users[0].rullenummer == "555"
        assert users[0].seniority_nr == 4

    def test_pdf_sync_skips_unmatched_row_with_no_db_write(self, patch_db, db_session):
        # PDF entries with no corresponding member-list user are not on the
        # NLF list — the sync must not create a stub for them.
        result = user_service.sync_employees_from_scrape([self.PDF_ROW])
        assert result["skipped_unmatched"] == 1
        assert db_session.query(DBUser).filter_by(name="Nordmann, Ola").count() == 0

        # A later member-list import creates the stub fresh, with no
        # rullenummer — the skipped PDF data was never persisted.
        report = user_service.sync_members_from_excel(
            [{"name": "Nordmann, Ola", "medlemsnummer": "60054"}]
        )
        assert report["created"] == 1

        users = db_session.query(DBUser).filter_by(name="Nordmann, Ola").all()
        assert len(users) == 1
        assert users[0].medlemsnummer == "60054"
        assert users[0].rullenummer is None


class TestFuzzyNameMatching:
    """NLF import fuzzy fallbacks for stubs created by old PDF sync."""

    def test_fuzzy_match_stub_with_middle_name(self, patch_db, db_session):
        # Old PDF stub has short first name; NLF has full name with middle name.
        add_user(db_session, "__stub_111", name="Andersen, Erik",
                 rullenummer="111", is_stub=1)
        report = user_service.sync_members_from_excel(
            [{"name": "Andersen, Erik Magnus", "medlemsnummer": "60099"}]
        )
        assert report["matched"] == 1
        assert report["created"] == 0
        db_session.expire_all()
        stub = db_session.query(DBUser).filter_by(rullenummer="111").first()
        assert stub is not None
        assert stub.name == "Andersen, Erik Magnus"
        assert stub.medlemsnummer == "60099"

    def test_fuzzy_match_stub_by_lastname_word_and_date(self, patch_db, db_session):
        # PDF stub has one part of a compound last name; NLF has both parts.
        add_user(db_session, "__stub_222", name="Nielsen, Kari",
                 rullenummer="222", ans_dato="01.01.2020", is_stub=1)
        report = user_service.sync_members_from_excel([{
            "name": "Nielsen Andersen, Kari",
            "medlemsnummer": "60100",
            "ans_dato": "01.01.2020",
        }])
        assert report["matched"] == 1
        assert report["created"] == 0
        db_session.expire_all()
        stub = db_session.query(DBUser).filter_by(rullenummer="222").first()
        assert stub is not None
        assert stub.name == "Nielsen Andersen, Kari"
        assert stub.medlemsnummer == "60100"

    def test_exact_match_absorbs_compound_lastname_stub(self, patch_db, db_session):
        # NLF has "Nyhagen, Ove" (short), PDF stub has "Farestveit Nyhagen, Ove"
        # with same ans_dato. The NLF row matches the NLF stub by exact name,
        # then absorb_fuzzy_twins should pull in the PDF stub's rullenummer.
        add_user(db_session, "__stub_m69496", name="Nyhagen, Ove",
                 medlemsnummer="69496", is_stub=1)
        add_user(db_session, "__stub_555", name="Farestveit Nyhagen, Ove",
                 rullenummer="555", ans_dato="30.10.2023", seniority_nr=10, is_stub=1)
        report = user_service.sync_members_from_excel([{
            "name": "Nyhagen, Ove",
            "medlemsnummer": "69496",
            "ans_dato": "30.10.2023",
        }])
        assert report["deleted_stubs"] == 1
        db_session.expire_all()
        users = db_session.query(DBUser).filter_by(name="Nyhagen, Ove").all()
        assert len(users) == 1
        assert users[0].medlemsnummer == "69496"
        assert users[0].rullenummer == "555"
        assert users[0].seniority_nr == 10

    def test_fuzzy_match_ambiguous_does_not_merge(self, patch_db, db_session):
        # Two stubs with the same last-name word and date → ambiguous, create new stub.
        add_user(db_session, "__stub_333", name="Hansen, Per",
                 rullenummer="333", ans_dato="05.05.2018", is_stub=1)
        add_user(db_session, "__stub_334", name="Hansen, Per",
                 rullenummer="334", ans_dato="05.05.2018", is_stub=1)
        report = user_service.sync_members_from_excel([{
            "name": "Hansen, Per Erik",
            "medlemsnummer": "60101",
            "ans_dato": "05.05.2018",
        }])
        assert report["created"] == 1
        assert report["matched"] == 0
