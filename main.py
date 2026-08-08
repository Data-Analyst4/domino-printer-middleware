#!/usr/bin/env python3
"""Domino Ax Codenet printer middleware — separate from Rynan middleware."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import Flask
from flask_cors import CORS

from app.api.routes import api
from app.core.bootstrap import init_app, shutdown_app
from app.utils.logger import log
from app.version import VERSION, get_version_info


def create_app() -> Flask:
    ctx = init_app()
    app = Flask(__name__)
    CORS(app, origins=ctx.settings.cors_origins)
    app.register_blueprint(api)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Domino Printer Middleware")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        info = get_version_info()
        print(f"Domino Printer Middleware v{info['version']} ({info['build']})")
        return

    app = create_app()
    from app.core.bootstrap import get_context

    ctx = get_context()
    host = args.host or ctx.settings.host
    port = args.port or ctx.settings.port

    log(f"Starting Domino Printer Middleware v{VERSION} on http://{host}:{port}")

    try:
        if args.debug:
            app.run(host=host, port=port, debug=True, threaded=True)
        else:
            try:
                from waitress import serve

                log("Using Waitress WSGI server")
                serve(app, host=host, port=port, threads=8)
            except ImportError:
                log("Waitress not installed; using Flask threaded server", level="WARNING")
                app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        shutdown_app()


if __name__ == "__main__":
    main()
