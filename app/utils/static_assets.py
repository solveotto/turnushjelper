"""Versioned URLs for everything under app/static/.

nginx serves /static/ itself with a 30-day max-age, while pages are no-store,
so after a deploy browsers kept running old cached JS/CSS against new markup
(the strekliste modal went blank on staging, 2026-10-25). The ``static``
endpoint therefore lives at /assets/<version>/<path>, where the version
fingerprints the files. Relative ES-module imports and CSS @imports resolve
under the same prefix, so changing any file gives every asset a URL no browser
has cached. The prefix is not "/static-<version>", which nginx's /static rule
could also match.
"""

import hashlib
import os

from flask import Flask, g, send_from_directory

ASSET_URL_PREFIX = "/assets/"
LEGACY_STATIC_PREFIX = "/static/"

# A versioned URL never changes content, so browsers may keep it for good
ASSET_MAX_AGE = 365 * 24 * 3600


def compute_asset_version(static_dir: str) -> str:
    """Fingerprint of the path, size and mtime of every file under static_dir."""
    digest = hashlib.sha1()
    for root, dirs, files in os.walk(static_dir):
        dirs.sort()  # walk order must not depend on the filesystem
        for name in sorted(files):
            path = os.path.join(root, name)
            stat = os.stat(path)
            rel = os.path.relpath(path, static_dir)
            digest.update(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:10]


def init_versioned_static(app: Flask, static_dir: str) -> None:
    """Register /assets/<version>/<path> as the ``static`` endpoint.

    The app must be created with static_folder=None, so Flask does not claim
    the endpoint name for its own /static route.
    """

    @app.route(f"{ASSET_URL_PREFIX}<version>/<path:filename>", endpoint="static")
    def versioned_static(version: str, filename: str):
        # Any version is served: a page rendered just before a deploy asks for
        # the old one, and the current file is the best answer to that
        response = send_from_directory(static_dir, filename, max_age=ASSET_MAX_AGE)
        response.cache_control.immutable = True
        return response

    # Unversioned paths as before. nginx answers these in production; this
    # covers dev for the few paths hardcoded in JS (img/bed.png, tour images).
    @app.route(f"{LEGACY_STATIC_PREFIX}<path:filename>", endpoint="legacy_static")
    def legacy_static(filename: str):
        return send_from_directory(static_dir, filename)

    @app.url_defaults
    def add_asset_version(endpoint: str, values: dict) -> None:
        if endpoint != "static" or "version" in values:
            return
        # Recomputed per request (~0.1 ms for 50 files) rather than once at
        # startup, so a JS/CSS edit shows without restarting the dev server
        if "asset_version" not in g:
            g.asset_version = compute_asset_version(static_dir)
        values["version"] = g.asset_version
