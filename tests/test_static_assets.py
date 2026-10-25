"""Versioned static URLs.

nginx serves /static/ with a 30-day max-age while the HTML is no-store, so
after a deploy browsers ran old cached JS against new markup: the strekliste
modal went blank on staging (2026-10-25, commit 1d3f52f). url_for('static')
now builds /assets/<version>/..., where the version fingerprints app/static/,
so any changed file gives every asset a URL no browser has cached.
"""

import re

from flask import url_for

from app.utils.static_assets import compute_asset_version
from tests.conftest import login_user

ASSET_URL = re.compile(r"^/assets/[0-9a-f]{10}/js/main\.js$")


class TestAssetUrls:
    def test_static_url_carries_version(self, app):
        with app.test_request_context():
            assert ASSET_URL.match(url_for("static", filename="js/main.js"))

    def test_rendered_page_links_versioned_assets(self, client):
        html = client.get("/login").get_data(as_text=True)
        assert re.search(r'/assets/[0-9a-f]{10}/', html)
        assert 'src="/static/' not in html and 'href="/static/' not in html


class TestAssetServing:
    def test_serves_file_with_long_immutable_cache(self, app, client):
        with app.test_request_context():
            url = url_for("static", filename="js/main.js")
        resp = client.get(url)
        assert resp.status_code == 200
        with open(f"{app.root_path}/static/js/main.js", "rb") as f:
            assert resp.data == f.read()
        cache_control = resp.headers["Cache-Control"]
        assert "max-age=31536000" in cache_control
        assert "immutable" in cache_control
        assert "no-cache" not in cache_control

    def test_stale_version_still_serves_current_file(self, client):
        # A page rendered just before a deploy asks for the old version
        resp = client.get("/assets/0000000000/js/main.js")
        assert resp.status_code == 200

    def test_path_traversal_refused(self, client):
        resp = client.get("/assets/0000000000/../../config.py")
        assert resp.status_code == 404

    def test_unversioned_static_path_still_served(self, client):
        # nginx serves /static/ in production; hardcoded paths in JS
        # (img/bed.png, tour images) rely on it, so dev must match
        resp = client.get("/static/img/bed.png")
        assert resp.status_code == 200
        assert "immutable" not in resp.headers.get("Cache-Control", "")

    def test_asset_request_skips_session(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get("/assets/0000000000/js/main.js")
        assert resp.status_code == 200
        assert "Set-Cookie" not in resp.headers


class TestComputeAssetVersion:
    def test_stable_when_nothing_changes(self, tmp_path):
        (tmp_path / "a.js").write_text("one")
        assert compute_asset_version(str(tmp_path)) == compute_asset_version(str(tmp_path))

    def test_changes_when_a_file_changes(self, tmp_path):
        (tmp_path / "a.js").write_text("one")
        before = compute_asset_version(str(tmp_path))
        (tmp_path / "a.js").write_text("one plus more")
        assert compute_asset_version(str(tmp_path)) != before

    def test_changes_when_a_file_is_added(self, tmp_path):
        (tmp_path / "a.js").write_text("one")
        before = compute_asset_version(str(tmp_path))
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.css").write_text("two")
        assert compute_asset_version(str(tmp_path)) != before
