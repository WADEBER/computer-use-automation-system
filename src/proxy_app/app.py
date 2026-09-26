"""Flask proxy target app for computer-use automation (Phase 2).

A local, deliberately realistic legacy-banking-style web UI used as the
automation target. No external dependencies beyond Flask.
"""

import os

from flask import Flask


def resolve_config() -> tuple[str, int, bool]:
    host = os.environ.get("PROXY_APP_HOST", "127.0.0.1")
    port = int(os.environ.get("PROXY_APP_PORT", "5000"))
    debug = os.environ.get("PROXY_APP_DEBUG", "").strip().lower() in {"1", "true", "yes"}
    return host, port, debug


def create_app() -> Flask:
    app = Flask(__name__)

    from proxy_app.routes import web

    app.register_blueprint(web)

    return app


def main() -> None:
    host, port, debug = resolve_config()
    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
