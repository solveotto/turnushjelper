"""Tests for the create_app() application factory.

Covers the ProxyFix wiring: in production (TRUSTED_PROXY_COUNT > 0) the app must
trust nginx's X-Forwarded-For so it sees the real client IP; in dev (count 0) it
must ignore the header so a client cannot spoof its IP.
"""

from werkzeug.middleware.proxy_fix import ProxyFix


def _build_app(monkeypatch, proxy_count):
    """Build a fresh app via the real factory with a given trusted-proxy count."""
    from config import AppConfig

    monkeypatch.setattr(AppConfig, "TRUSTED_PROXY_COUNT", proxy_count)
    # init_default_admin touches the DB; the app fixture pattern stubs it out.
    monkeypatch.setattr(
        "app.services.user_service.init_default_admin", lambda: None
    )
    from app import create_app

    return create_app()


class TestProxyFixWiring:
    def test_proxyfix_enabled_in_production(self, patch_db, monkeypatch):
        app = _build_app(monkeypatch, 1)
        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.wsgi_app.x_for == 1
        assert app.wsgi_app.x_proto == 1

    def test_proxyfix_honors_multiple_hops(self, patch_db, monkeypatch):
        # e.g. a CDN in front of nginx → two trusted hops.
        app = _build_app(monkeypatch, 2)
        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.wsgi_app.x_for == 2
        assert app.wsgi_app.x_proto == 2

    def test_proxyfix_disabled_without_proxy(self, patch_db, monkeypatch):
        app = _build_app(monkeypatch, 0)
        assert not isinstance(app.wsgi_app, ProxyFix)

    def test_forwarded_ip_reflected_when_enabled(self, patch_db, monkeypatch):
        app = _build_app(monkeypatch, 1)

        @app.route("/_whoami_enabled")
        def _whoami_enabled():
            from flask import request

            return request.remote_addr or "none"

        resp = app.test_client().get(
            "/_whoami_enabled", headers={"X-Forwarded-For": "93.40.1.2"}
        )
        assert resp.data == b"93.40.1.2"

    def test_forwarded_ip_ignored_when_disabled(self, patch_db, monkeypatch):
        app = _build_app(monkeypatch, 0)

        @app.route("/_whoami_disabled")
        def _whoami_disabled():
            from flask import request

            return request.remote_addr or "none"

        resp = app.test_client().get(
            "/_whoami_disabled", headers={"X-Forwarded-For": "93.40.1.2"}
        )
        # The forged header must NOT become the client IP.
        assert resp.data != b"93.40.1.2"
