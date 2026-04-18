from __future__ import annotations

from pathlib import Path

from flask import Flask

from ctfarena.blueprints.admin import bp as admin_bp
from ctfarena.blueprints.api import bp as api_bp
from ctfarena.config import Config
from ctfarena.db import init_app as init_db
from ctfarena.services.competition import CompetitionManager
from ctfarena.telemetry import init_sentry


def create_app(config_object: type[Config] = Config) -> Flask:
    from modules.frontend import frontend_bp

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    Path(app.config["INSTANCE_PATH"]).mkdir(parents=True, exist_ok=True)

    release = (
        f"ctfarena@{app.config['CTF_ARENA_COMMIT']}"
        f"+sandbox.{app.config['DEFAULT_SANDBOX_DIGEST'][-12:]}"
    )
    init_sentry(
        component="web",
        release=release,
        environment=app.config["SENTRY_ENVIRONMENT"],
    )
    init_db(app)

    app.extensions["competition_manager"] = CompetitionManager(app)

    app.register_blueprint(frontend_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        return {
            "app_name": "https://ctfarena.live/",
        }

    return app
