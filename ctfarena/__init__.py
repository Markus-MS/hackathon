from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from ctfarena.blueprints.admin import bp as admin_bp
from ctfarena.blueprints.api import bp as api_bp
from ctfarena.config import Config
from ctfarena.db import init_app as init_db
from ctfarena.services.competition import CompetitionManager
from ctfarena.telemetry import init_sentry


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def should_auto_resume_competitions() -> bool:
    setting = os.environ.get("CTF_ARENA_AUTO_RESUME", "1").lower()
    if setting in {"0", "false", "no", "off"}:
        return False
    debug_reloader = _truthy_env("CTF_ARENA_DEBUG") or _truthy_env("FLAGFARM_DEBUG")
    if debug_reloader and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


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

    competition_manager = CompetitionManager(app)
    app.extensions["competition_manager"] = competition_manager

    app.register_blueprint(frontend_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    if should_auto_resume_competitions():
        competition_manager.resume_incomplete_runs()

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        return {
            "app_name": "https://ctfarena.live/",
        }

    return app
