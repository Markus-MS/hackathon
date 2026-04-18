#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "flask",
#   "openfeature-sdk",
#   "requests",
#   "sentry-sdk",
# ]
# ///

import logging
import os
import random
import time
from html import escape
from typing import Any

import requests
import sentry_sdk
from flask import Flask, Response, has_request_context, jsonify, request
from openfeature import api as openfeature_api
from openfeature.provider import AbstractProvider, FlagResolutionDetails, Metadata
from sentry_sdk import metrics
from sentry_sdk.crons.decorator import monitor
from sentry_sdk.integrations.openfeature import OpenFeatureIntegration


DSN = os.environ.get(
    "SENTRY_DSN",
    "https://f271196a290a90a866d33acb56d25eed@o4511239870939136.ingest.de.sentry.io/4511240223653968",
)
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))
ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", "hackathon")
RELEASE = os.environ.get("SENTRY_RELEASE", "sentry-flask-starter@1.0.0")
SERVER_NAME = os.environ.get("SENTRY_SERVER_NAME", "sentry-flask-starter")
PUBLIC_KEY = DSN.split("//", 1)[1].split("@", 1)[0] if "//" in DSN and "@" in DSN else ""


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)


class StaticFlagProvider(AbstractProvider):
    def get_metadata(self) -> Metadata:
        return Metadata(name="static-hackathon-provider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context=None,
    ) -> FlagResolutionDetails[bool]:
        flags = {
            "new-checkout": True,
            "beta-dashboard": True,
            "danger-mode": False,
        }
        return FlagResolutionDetails(
            value=flags.get(flag_key, default_value),
            reason="STATIC",
            variant="enabled" if flags.get(flag_key, default_value) else "disabled",
        )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context=None,
    ) -> FlagResolutionDetails[str]:
        values = {
            "theme": "sentry-red",
            "checkout-flow": "fast-lane",
        }
        return FlagResolutionDetails(
            value=values.get(flag_key, default_value),
            reason="STATIC",
            variant=flag_key,
        )

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context=None,
    ) -> FlagResolutionDetails[int]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context=None,
    ) -> FlagResolutionDetails[float]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Any,
        evaluation_context=None,
    ) -> FlagResolutionDetails[Any]:
        return FlagResolutionDetails(value=default_value, reason="STATIC", variant=flag_key)


def traces_sampler(sampling_context: dict[str, Any]) -> float:
    path = request.path if has_request_context() else None
    if path == "/health":
        return 0.0
    return 1.0


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    event.setdefault("tags", {})
    event["tags"]["demo"] = "sentry-flask-starter"
    event["tags"]["hackathon"] = "true"
    return event


openfeature_api.set_provider(StaticFlagProvider())

sentry_sdk.init(
    dsn=DSN,
    environment=ENVIRONMENT,
    release=RELEASE,
    server_name=SERVER_NAME,
    send_default_pii=True,
    enable_logs=True,
    traces_sampler=traces_sampler,
    profile_session_sample_rate=1.0,
    profile_lifecycle="trace",
    attach_stacktrace=True,
    integrations=[OpenFeatureIntegration()],
    before_send=before_send,
)


app = Flask(__name__)


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sentry Hackathon Demo</title>
    <script
      src="https://js.sentry-cdn.com/__PUBLIC_KEY__.min.js"
      crossorigin="anonymous"
    ></script>
    <style>
      :root {
        color-scheme: dark;
        --bg: #120d0d;
        --bg-soft: #201212;
        --panel: rgba(33, 18, 18, 0.88);
        --line: rgba(255, 208, 208, 0.14);
        --text: #fff4ef;
        --muted: #d7b8b1;
        --red: #ff5b47;
        --orange: #ff9a3c;
        --gold: #ffd166;
        --teal: #65f0d2;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        font-family: "Space Grotesk", "IBM Plex Sans", sans-serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(255, 91, 71, 0.28), transparent 28%),
          radial-gradient(circle at 80% 10%, rgba(255, 154, 60, 0.2), transparent 26%),
          radial-gradient(circle at bottom right, rgba(101, 240, 210, 0.12), transparent 25%),
          linear-gradient(135deg, #160f0f 0%, #1f1211 48%, #100c0d 100%);
        min-height: 100vh;
      }

      .wrap {
        width: min(1180px, calc(100vw - 28px));
        margin: 18px auto 40px;
      }

      .hero {
        position: relative;
        overflow: hidden;
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 26px;
        background:
          linear-gradient(135deg, rgba(255, 91, 71, 0.16), rgba(255, 154, 60, 0.09) 40%, rgba(0, 0, 0, 0) 90%),
          var(--panel);
        box-shadow: 0 28px 90px rgba(0, 0, 0, 0.34);
      }

      .hero::after {
        content: "";
        position: absolute;
        inset: auto -10% -40% auto;
        width: 380px;
        height: 380px;
        border-radius: 999px;
        background: radial-gradient(circle, rgba(255, 91, 71, 0.18), transparent 65%);
        pointer-events: none;
      }

      .eyebrow {
        display: inline-flex;
        gap: 10px;
        align-items: center;
        padding: 7px 11px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.06);
        color: var(--gold);
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      h1 {
        margin: 16px 0 10px;
        font-size: clamp(2.4rem, 6vw, 5rem);
        line-height: 0.95;
        letter-spacing: -0.05em;
        max-width: 10ch;
      }

      .lede {
        margin: 0;
        max-width: 64ch;
        color: var(--muted);
        font-size: 1.05rem;
        line-height: 1.6;
      }

      .hero-grid,
      .panel-grid {
        display: grid;
        gap: 16px;
        margin-top: 22px;
      }

      .hero-grid {
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      }

      .stat,
      .panel {
        border: 1px solid var(--line);
        border-radius: 22px;
        background: rgba(16, 10, 10, 0.78);
      }

      .stat {
        padding: 16px;
      }

      .stat-label {
        color: var(--muted);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.12em;
      }

      .stat-value {
        margin-top: 10px;
        font-size: 1.65rem;
        font-weight: 700;
      }

      .panel-grid {
        grid-template-columns: 1.3fr 0.9fr;
      }

      .panel {
        padding: 20px;
      }

      .panel h2 {
        margin: 0 0 6px;
        font-size: 1rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }

      .panel p {
        margin: 0 0 18px;
        color: var(--muted);
        line-height: 1.5;
      }

      .button-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
      }

      button,
      .link-card {
        appearance: none;
        width: 100%;
        border: 0;
        text-align: left;
        padding: 14px 14px 13px;
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
        color: var(--text);
        border: 1px solid rgba(255,255,255,0.07);
        cursor: pointer;
        transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
      }

      button:hover,
      .link-card:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 154, 60, 0.4);
        background: linear-gradient(180deg, rgba(255,154,60,0.12), rgba(255,255,255,0.03));
      }

      button strong,
      .link-card strong {
        display: block;
        margin-bottom: 4px;
        font-size: 0.95rem;
      }

      button span,
      .link-card span {
        display: block;
        color: var(--muted);
        font-size: 0.88rem;
        line-height: 1.4;
      }

      .link-stack {
        display: grid;
        gap: 12px;
      }

      .link-card {
        text-decoration: none;
      }

      .log {
        margin-top: 16px;
        min-height: 210px;
        max-height: 360px;
        overflow: auto;
        padding: 14px;
        border-radius: 16px;
        background: #0e0909;
        border: 1px solid rgba(255,255,255,0.06);
        font-family: "IBM Plex Mono", monospace;
        font-size: 13px;
        line-height: 1.55;
        white-space: pre-wrap;
      }

      .pulse {
        display: inline-block;
        width: 10px;
        height: 10px;
        margin-right: 8px;
        border-radius: 999px;
        background: var(--teal);
        box-shadow: 0 0 0 rgba(101, 240, 210, 0.6);
        animation: pulse 1.6s infinite;
      }

      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(101, 240, 210, 0.55); }
        70% { box-shadow: 0 0 0 14px rgba(101, 240, 210, 0); }
        100% { box-shadow: 0 0 0 0 rgba(101, 240, 210, 0); }
      }

      @media (max-width: 900px) {
        .panel-grid {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero">
        <div class="eyebrow"><span class="pulse"></span>Sentry Hackathon Demo</div>
        <h1>Make the Sentry UI light up.</h1>
        <p class="lede">
          This page generates frontend errors, backend errors, distributed traces, logs, metrics,
          cron check-ins, feature flags, and feedback-oriented traffic so your Sentry project looks alive
          instead of only showing one lonely Flask exception.
        </p>

        <div class="hero-grid">
          <div class="stat">
            <div class="stat-label">Environment</div>
            <div class="stat-value">__ENVIRONMENT__</div>
          </div>
          <div class="stat">
            <div class="stat-label">Release</div>
            <div class="stat-value">__RELEASE__</div>
          </div>
          <div class="stat">
            <div class="stat-label">Backend</div>
            <div class="stat-value">Flask + Python SDK</div>
          </div>
          <div class="stat">
            <div class="stat-label">Frontend</div>
            <div class="stat-value">Browser SDK + Trace Hooks</div>
          </div>
        </div>
      </section>

      <section class="panel-grid">
        <section class="panel">
          <h2>Trigger Demo Signals</h2>
          <p>Use the buttons below during the demo. Each one is designed to land in a different part of Sentry.</p>
          <div class="button-grid">
            <button data-action="frontend-message"><strong>Frontend Message</strong><span>Create a browser-side message event.</span></button>
            <button data-action="frontend-error"><strong>Frontend Error</strong><span>Throw and capture a browser exception.</span></button>
            <button data-action="frontend-rejection"><strong>Promise Rejection</strong><span>Create an unhandled browser rejection.</span></button>
            <button data-action="frontend-span"><strong>Frontend Span</strong><span>Record a custom browser span with fake work.</span></button>
            <button data-action="backend-message"><strong>Backend Message</strong><span>Manual server message event.</span></button>
            <button data-action="backend-error"><strong>Backend Error</strong><span>Unhandled Flask exception for Issues.</span></button>
            <button data-action="trace"><strong>Distributed Trace</strong><span>Browser to Flask request with nested spans.</span></button>
            <button data-action="logs"><strong>Logs</strong><span>Ship Python logs into Sentry Logs.</span></button>
            <button data-action="metrics"><strong>Metrics</strong><span>Emit gauges, counters, distributions.</span></button>
            <button data-action="flags"><strong>Feature Flags</strong><span>Capture OpenFeature evaluations.</span></button>
            <button data-action="cron"><strong>Cron Check-In</strong><span>Send a cron monitor event.</span></button>
            <button data-action="smoke"><strong>Full Smoke</strong><span>Fire several high-signal backend features at once.</span></button>
          </div>
          <div id="log" class="log">Waiting for demo actions…</div>
        </section>

        <aside class="panel">
          <h2>Where To Look In Sentry</h2>
          <p>The custom dashboard is not the whole product. For the most visible demo, jump across these views while clicking buttons.</p>
          <div class="link-stack">
            <a class="link-card" href="__DASHBOARD_URL__" target="_blank" rel="noreferrer">
              <strong>Dashboard</strong>
              <span>Your custom dashboard. Great once you save useful span queries as widgets.</span>
            </a>
            <a class="link-card" href="https://ernesto-az.sentry.io/explore/traces/?environment=hackathon&project=4511240223653968" target="_blank" rel="noreferrer">
              <strong>Trace Explorer</strong>
              <span>Best place to show backend and browser transactions, spans, and distributed traces.</span>
            </a>
            <a class="link-card" href="https://ernesto-az.sentry.io/issues/?environment=hackathon&project=4511240223653968" target="_blank" rel="noreferrer">
              <strong>Issues</strong>
              <span>Shows the unhandled Flask error and browser-side exceptions.</span>
            </a>
            <a class="link-card" href="https://ernesto-az.sentry.io/explore/logs/?environment=hackathon&project=4511240223653968" target="_blank" rel="noreferrer">
              <strong>Logs</strong>
              <span>Shows structured Python log events from the backend routes.</span>
            </a>
          </div>
        </aside>
      </section>
    </main>

    <script>
      const logEl = document.getElementById("log");
      const dashboardUrl = "__DASHBOARD_URL__";

      function log(message, payload) {
        const ts = new Date().toLocaleTimeString();
        const line = `[${ts}] ${message}` + (payload ? `\\n${JSON.stringify(payload, null, 2)}` : "");
        logEl.textContent = `${line}\\n\\n${logEl.textContent}`.trim();
      }

      function fakeCpuWork(ms) {
        const start = performance.now();
        while (performance.now() - start < ms) {
          Math.sqrt(Math.random() * 1000);
        }
      }

      if (window.Sentry) {
        const integrations = [];
        if (typeof window.Sentry.browserTracingIntegration === "function") {
          integrations.push(window.Sentry.browserTracingIntegration());
        }
        if (typeof window.Sentry.replayIntegration === "function") {
          integrations.push(window.Sentry.replayIntegration({ maskAllText: false, blockAllMedia: false }));
        }
        if (typeof window.Sentry.feedbackIntegration === "function") {
          integrations.push(window.Sentry.feedbackIntegration({
            colorScheme: "dark",
            showBranding: false,
            autoInject: true,
          }));
        }

        window.Sentry.init({
          dsn: "__DSN__",
          environment: "__ENVIRONMENT__",
          release: "__RELEASE__",
          integrations,
          tracesSampleRate: 1.0,
          replaysSessionSampleRate: 1.0,
          replaysOnErrorSampleRate: 1.0,
          sendDefaultPii: true,
          tracePropagationTargets: ["localhost", /^http:\\/\\/127\\.0\\.0\\.1:__PORT__/, /^http:\\/\\/localhost:__PORT__/],
          initialScope: {
            tags: {
              surface: "browser",
              hackathon: "true",
            },
          },
          beforeSend(event) {
            event.tags = event.tags || {};
            event.tags.demo_page = "sentry-hackathon";
            return event;
          },
        });

        window.Sentry.setUser({
          id: "browser-demo-user",
          email: "browser-demo@example.com",
          username: "browser-demo-user",
        });
        window.Sentry.setTag("demo_mode", "hackathon");
        window.Sentry.setContext("hackathon_ui", {
          page: "demo-home",
          dashboardUrl,
        });
        log("Browser SDK initialized");
      } else {
        log("Browser SDK failed to load");
      }

      async function fetchJson(path) {
        const response = await fetch(path, { headers: { "X-Request-Id": crypto.randomUUID() } });
        const text = await response.text();
        let data = text;
        try {
          data = JSON.parse(text);
        } catch (_) {}
        log(`${response.status} ${path}`, data);
        return { response, data };
      }

      async function runAction(action) {
        if (!window.Sentry) {
          log("Sentry browser SDK unavailable");
          return;
        }

        switch (action) {
          case "frontend-message": {
            window.Sentry.captureMessage("Frontend hackathon message", "warning");
            log("Captured browser message event");
            break;
          }
          case "frontend-error": {
            try {
              throw new Error("Frontend hackathon exception");
            } catch (error) {
              window.Sentry.captureException(error);
              log("Captured browser exception", { name: error.name, message: error.message });
            }
            break;
          }
          case "frontend-rejection": {
            Promise.reject(new Error("Frontend unhandled rejection for Sentry demo"));
            log("Scheduled unhandled promise rejection");
            break;
          }
          case "frontend-span": {
            if (typeof window.Sentry.startSpan === "function") {
              await window.Sentry.startSpan({ name: "ui.render-demo", op: "ui.action" }, async () => {
                fakeCpuWork(180);
                await new Promise((resolve) => setTimeout(resolve, 220));
              });
              log("Captured browser custom span");
            } else {
              fakeCpuWork(200);
              log("Browser SDK has no startSpan; performed local work only");
            }
            break;
          }
          case "backend-message":
            await fetchJson("/message");
            break;
          case "backend-error":
            await fetchJson("/debug-sentry");
            break;
          case "trace":
            await fetchJson("/trace");
            break;
          case "logs":
            await fetchJson("/logs");
            break;
          case "metrics":
            await fetchJson("/metrics");
            break;
          case "flags":
            await fetchJson("/feature-flags");
            break;
          case "cron":
            await fetchJson("/cron");
            break;
          case "smoke":
            await fetchJson("/smoke");
            break;
          default:
            log(`Unknown action: ${action}`);
        }
      }

      document.querySelectorAll("[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const { action } = button.dataset;
          window.Sentry?.addBreadcrumb({
            category: "ui.click",
            message: `clicked:${action}`,
            level: "info",
          });
          runAction(action);
        });
      });
    </script>
  </body>
</html>
"""


def base_url() -> str:
    return f"http://{HOST}:{PORT}"


def annotate_request(scope) -> None:
    user_id = request.args.get("user", "hackathon-user")
    tier = request.args.get("tier", "pro")
    scope.set_user(
        {
            "id": user_id,
            "username": user_id,
            "email": f"{user_id}@example.com",
            "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
            "segment": tier,
        }
    )
    scope.set_tag("route", request.path)
    scope.set_tag("hackathon", "true")
    scope.set_tag("request_id", request.headers.get("X-Request-Id", "demo-request"))
    scope.set_context(
        "feature_flags",
        {
            "new-checkout": True,
            "beta-dashboard": True,
            "danger-mode": False,
        },
    )
    scope.set_context(
        "request_demo",
        {
            "method": request.method,
            "path": request.path,
            "args": dict(request.args),
        },
    )
    scope.set_extra("query_args", dict(request.args))
    scope.add_attachment(
        bytes=f"route={request.path}\nargs={dict(request.args)}\n".encode(),
        filename="request.txt",
        content_type="text/plain",
    )


def instrument_demo(name: str) -> None:
    with sentry_sdk.start_span(op="demo.step", name=f"{name}.db"):
        time.sleep(0.03)
    with sentry_sdk.start_span(op="demo.step", name=f"{name}.compute"):
        time.sleep(0.02)


@monitor(monitor_slug="hackathon-demo-checkin")
def run_monitored_job() -> dict[str, Any]:
    with sentry_sdk.start_span(op="job.fetch", name="load inputs"):
        time.sleep(0.02)
    with sentry_sdk.start_span(op="job.process", name="process inputs"):
        time.sleep(0.02)
    return {"monitor": "sent", "slug": "hackathon-demo-checkin"}


@app.before_request
def add_breadcrumb() -> None:
    sentry_sdk.add_breadcrumb(
        category="http",
        type="http",
        level="info",
        message=f"{request.method} {request.path}",
        data={"args": dict(request.args)},
    )


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status=204)


@app.get("/")
def index():
    page = (
        HTML.replace("__PUBLIC_KEY__", escape(PUBLIC_KEY))
        .replace("__DSN__", escape(DSN))
        .replace("__ENVIRONMENT__", escape(ENVIRONMENT))
        .replace("__RELEASE__", escape(RELEASE))
        .replace("__PORT__", str(PORT))
        .replace(
            "__DASHBOARD_URL__",
            "https://ernesto-az.sentry.io/dashboard/1733119/?environment=hackathon&project=4511240223653968",
        )
    )
    return Response(page, mimetype="text/html")


@app.get("/api")
def api_index():
    return jsonify(
        service="sentry-flask-starter",
        environment=ENVIRONMENT,
        release=RELEASE,
        endpoints={
            "/": "interactive Sentry demo homepage",
            "/health": "low-noise health route, excluded from tracing",
            "/message": "capture a manual Sentry message with request context",
            "/handled": "capture a handled exception",
            "/debug-sentry": "raise an unhandled exception",
            "/logs": "send structured logs to Sentry",
            "/metrics": "emit count, gauge, and distribution metrics",
            "/trace": "custom transaction, spans, and outbound HTTP request",
            "/feedback": "manual user-facing feedback event",
            "/cron": "send a cron monitor check-in",
            "/feature-flags": "evaluate OpenFeature flags with Sentry integration",
            "/smoke": "trigger several useful signals in one request",
        },
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/message")
def message():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_level("warning")
        event_id = sentry_sdk.capture_message("Hackathon test message from Flask", level="warning")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="message", event_id=event_id)


@app.get("/handled")
def handled():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_tag("error_kind", "handled")
        try:
            raise RuntimeError("Handled exception for Sentry demo")
        except RuntimeError as exc:
            event_id = sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="handled_exception", event_id=event_id)


@app.get("/debug-sentry")
def debug_sentry():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        scope.set_tag("error_kind", "unhandled")
        instrument_demo("debug-sentry")
        1 / 0


@app.get("/logs")
def logs():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        sentry_sdk.logger.info("Sentry logger info", route=request.path)
        sentry_sdk.logger.warning("Sentry logger warning", route=request.path)
        sentry_sdk.logger.error("Sentry logger error", route=request.path)
        logger.info("Python logging info for Sentry")
        logger.warning("Python logging warning for Sentry")
        logger.error("Python logging error for Sentry")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="logs")


@app.get("/metrics")
def emit_metrics():
    amount = round(random.uniform(25, 250), 2)
    queue_depth = random.randint(1, 50)
    user_id = request.args.get("user", "hackathon-user")
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        metrics.count("checkout.started", 1, attributes={"env": ENVIRONMENT})
        metrics.count("checkout.failed", 1, attributes={"env": ENVIRONMENT, "flow": "fast-lane"})
        metrics.gauge("queue.depth", queue_depth, attributes={"env": ENVIRONMENT})
        metrics.distribution("cart.amount_usd", amount, attributes={"env": ENVIRONMENT})
        metrics.distribution("users.name_length", len(user_id), attributes={"env": ENVIRONMENT})
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="metrics", amount=amount, queue_depth=queue_depth)


@app.get("/trace")
def trace():
    with sentry_sdk.start_transaction(name="hackathon.trace", op="http.server") as transaction:
        with sentry_sdk.new_scope() as scope:
            annotate_request(scope)
            instrument_demo("trace")
            response = requests.get(f"{base_url()}/health", timeout=3)
            transaction.set_tag("health_status", response.status_code)
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="trace", downstream_status=response.status_code)


@app.get("/feedback")
def feedback():
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        event_id = sentry_sdk.capture_message("User feedback submitted", level="info")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(
        status="captured",
        type="feedback_seed",
        event_id=event_id,
        note="Use this event_id with the Sentry user feedback UI/API.",
    )


@app.get("/cron")
def cron():
    payload = run_monitored_job()
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="cron", **payload)


@app.get("/feature-flags")
def feature_flags():
    client = openfeature_api.get_client()
    with sentry_sdk.new_scope() as scope:
        annotate_request(scope)
        new_checkout = client.get_boolean_value("new-checkout", False)
        beta_dashboard = client.get_boolean_value("beta-dashboard", False)
        theme = client.get_string_value("theme", "default")
    sentry_sdk.flush(timeout=2.0)
    return jsonify(
        status="captured",
        type="feature_flags",
        flags={
            "new-checkout": new_checkout,
            "beta-dashboard": beta_dashboard,
            "theme": theme,
        },
    )


@app.get("/smoke")
def smoke():
    results = {
        "message": message().json,
        "handled": handled().json,
        "logs": logs().json,
        "metrics": emit_metrics().json,
        "trace": trace().json,
        "feature_flags": feature_flags().json,
        "cron": cron().json,
    }
    sentry_sdk.flush(timeout=2.0)
    return jsonify(status="captured", type="smoke", results=results)


def main():
    logger.info("Starting Sentry Flask demo on http://%s:%s", HOST, PORT)
    logger.info("Sentry environment=%s release=%s server_name=%s", ENVIRONMENT, RELEASE, SERVER_NAME)
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
