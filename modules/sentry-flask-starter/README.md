# Sentry Flask Starter

This module is a sample app for exploring Sentry features before integrating them into a real web application.

The code in [server.py](/home/ecomaikgolf/ctf/hackathon/modules/sentry-flask-starter/server.py) is intentionally demo-heavy. It is useful for learning what Sentry can capture, but it is not a production blueprint as-is.

## Goals

Use this module to:

- see which Sentry features are available in a Flask app
- verify what lands in the Sentry UI
- decide which features belong in the real product
- reuse small integration patterns later in the real app

Do not use this module to:

- copy every endpoint and demo route into production
- keep `100%` sampling settings in production
- ship demo-only user data, attachments, or synthetic events

## Run The Sample

```sh
chmod +x server.py
PORT=10001 ./server.py
```

Open `http://127.0.0.1:10001/`.

## What The Sample Demonstrates

The sample app currently demonstrates:

- Flask SDK initialization
- request breadcrumbs
- user, tags, extra data, and context enrichment
- manual messages
- handled and unhandled exceptions
- Python logs forwarded to Sentry
- custom metrics
- custom transactions and spans
- distributed tracing from browser to Flask
- profiling tied to traces
- cron monitor check-ins
- feature flag tracking through OpenFeature
- a browser page that triggers frontend and backend demo activity

## Real Integration Plan

For a proper webapp, integrate features in layers instead of trying to turn on everything blindly on day one.

### 1. Core Error Monitoring

Always start here.

Use:

- `sentry_sdk.init(...)` during app startup, before the Flask app is initialized
- `dsn`, `environment`, `release`, `server_name`
- Flask integration
- exception capture for both unhandled and important handled errors

Why:

- this gives immediate value in Issues
- it is the lowest-risk integration
- it creates the base for traces, logs, and release correlation later

Production guidance:

- keep error capture on by default
- use `before_send` only for scrubbing or dropping known-noise events
- do not inject fake errors or test routes into the real app

### 2. Release, Environment, And Ownership Metadata

Use:

- `release` tied to your git SHA, build ID, or deploy version
- `environment` such as `dev`, `staging`, `prod`
- `server_name` only if it is meaningful in your deployment model
- tags for tenant, region, product area, or request class

Why:

- this makes Issues and Traces filterable
- it makes deploy regressions visible
- it is required if you want Releases to be useful

Production guidance:

- release values should come from CI/CD, not hardcoded strings
- environment names should be stable and few
- avoid high-cardinality tags like arbitrary IDs unless you really need them

### 3. User Context

Use:

- `set_user(...)` for logged-in users or service identities

Good fields:

- internal user ID
- username
- tenant or plan
- email only if your privacy policy allows it

Why:

- helps support and debugging
- useful for grouping incidents by affected user segment

Production guidance:

- only send PII you are allowed to store
- if privacy is strict, send internal IDs and plan/segment only
- review `send_default_pii=True` carefully before using it in production

### 4. Structured Context

Use:

- `set_tag(...)`
- `set_context(...)`
- `set_extra(...)`
- breadcrumbs for important request and UX actions

Good examples:

- checkout flow name
- experiment bucket
- payment provider
- API route family
- feature flag state

Why:

- gives issues and traces enough context to explain behavior

Production guidance:

- tags should be low-cardinality and filter-friendly
- large blobs belong in context, not tags
- avoid dumping full request bodies, secrets, or tokens

### 5. Tracing And Performance

Use:

- tracing for web requests
- custom spans around expensive DB, cache, third-party API, queue, or AI calls
- trace propagation between browser and backend and across services

Why:

- this is what makes Trace Explorer useful
- it turns “something is slow” into “this dependency is slow”

Production guidance:

- do not keep `traces_sample_rate=1.0` in production unless traffic is tiny
- prefer a sampler or a lower sample rate
- instrument meaningful operations only
- name transactions and spans consistently

Recommended production targets:

- trace all staging traffic
- trace a sampled subset of production traffic
- always trace high-value or high-risk flows if volume allows

### 6. Profiling

Use:

- profiling only when you need deeper performance diagnostics
- profile sampling tied to traced requests

Why:

- useful for CPU-heavy code paths
- especially useful when tracing shows slowness but not why

Production guidance:

- sample conservatively
- keep it enabled for endpoints where CPU or serialization cost matters

### 7. Logs

Use:

- Python `logging`
- Sentry log ingestion if you want logs correlated with issues and traces

Why:

- logs become much more useful when attached to the same request context

Production guidance:

- log meaningful events, not everything
- prefer structured logs
- avoid duplicate noise by choosing clear logger levels
- do not emit fake demo logs in production

### 8. Metrics

Use:

- counters for event counts
- gauges for current point-in-time values
- distributions for value spreads like latency or cart size

Good examples:

- checkout failures
- queue depth
- search latency
- response payload size
- AI token usage

Why:

- metrics show trends better than single events

Production guidance:

- keep metric names stable
- use dimensions sparingly
- choose dimensions that are analytically useful, like env, route family, or provider

### 9. Cron Monitoring

Use:

- Sentry cron monitors for scheduled jobs, batch tasks, or data syncs

Why:

- jobs often fail silently outside the request/response path

Production guidance:

- instrument every important scheduled task
- use stable monitor slugs
- make sure retries and overlapping runs are understood before alerting

### 10. Feature Flags

Use:

- feature flag instrumentation if the real app uses LaunchDarkly, OpenFeature, Unleash, or another flag system

Why:

- this lets you correlate errors and regressions with experiments and rollout state

Production guidance:

- capture evaluation results for important flags only
- avoid flooding Sentry with every minor UI toggle

### 11. Frontend Browser Instrumentation

For a real webapp, this is the highest-value next step after backend Sentry.

Use:

- Sentry browser SDK in the frontend
- browser error monitoring
- browser tracing
- replay if the team is comfortable with the privacy implications
- feedback widget if you want rich demo value and product feedback

Why:

- frontend issues, replay, and browser traces make Sentry feel much more complete
- it also makes the Sentry Toolbar meaningful

Production guidance:

- review masking and privacy settings before enabling replay
- enable replay on a sample of sessions or on error
- propagate traces from browser to backend

## Suggested Rollout Order For The Real App

1. Core Flask error monitoring
2. Release and environment wiring
3. User and request context
4. Backend tracing and custom spans
5. Browser SDK with trace propagation
6. Logs
7. Metrics
8. Cron monitors
9. Feature flag instrumentation
10. Replay and feedback, if privacy and UX requirements allow it

## What To Copy From This Sample

Good candidates to reuse:

- early `sentry_sdk.init(...)`
- request enrichment patterns
- custom span patterns around expensive work
- cron monitor wrapper patterns
- feature flag integration structure
- browser-to-backend trace propagation ideas

Things to rewrite for production:

- hardcoded DSN
- `1.0` sample rates
- demo routes like `/debug-sentry` and `/smoke`
- synthetic metric names and demo log messages
- demo HTML page
- any broad PII capture without policy review

## Recommended Production Decisions

Before integrating into the real app, decide:

- which environments send to Sentry
- which PII is allowed
- which flows should always be traced
- which logs are worth ingesting
- which scheduled jobs need monitors
- whether replay is acceptable legally and operationally
- which feature flag provider should be instrumented

## Keys And Tokens Needed

For a proper integration, not every Sentry feature needs a secret key. Most runtime instrumentation only needs the DSN.

### 1. DSN

Needed for:

- Flask/Python SDK
- browser SDK
- tracing, profiling, logs, metrics, cron check-ins, and most runtime SDK features

Notes:

- the DSN is the main runtime ingest value
- the browser uses the public part of the DSN
- the backend can use the full DSN
- DSN values are not treated like high-risk admin secrets, but they still should not be hardcoded across the real codebase

Recommended env vars:

- `SENTRY_DSN`
- `NEXT_PUBLIC_SENTRY_DSN` or similar for frontend frameworks

### 2. Sentry Auth Token

Needed for:

- CI/CD release automation
- source map upload
- release creation/finalization
- deploy registration
- some management API workflows

Notes:

- this is a real secret
- do not expose it in frontend code
- do not ship it in the repo

Recommended env vars:

- `SENTRY_AUTH_TOKEN`

### 3. Organization And Project Identifiers

Often needed for:

- Sentry CLI
- release automation
- source map upload
- API-based setup scripts

Recommended env vars:

- `SENTRY_ORG`
- `SENTRY_PROJECT`

Notes:

- these are identifiers, not secrets
- still keep them in CI or deployment config rather than hardcoding them everywhere

### 4. Browser Public Key

Needed for:

- browser CDN/script-tag setups that use the public DSN key directly

Notes:

- this is derived from the DSN
- it is public by design
- it is not enough for admin access to Sentry

### 5. Feature Flag Provider Keys

Needed only if the real app integrates a real feature flag service.

Examples:

- LaunchDarkly SDK key
- Unleash API token
- OpenFeature provider-specific credentials

Notes:

- these are not Sentry keys, but Sentry feature-flag correlation depends on that provider being configured correctly

### 6. Replay / Feedback / Toolbar

Needed for:

- usually no separate Sentry key beyond the DSN

Notes:

- these features are mostly SDK configuration decisions, not extra credential problems
- the main real requirement is privacy review, not more secrets

## Minimal Credential Set By Use Case

### Backend-only error monitoring

Need:

- `SENTRY_DSN`

### Backend + frontend instrumentation

Need:

- backend `SENTRY_DSN`
- frontend public DSN exposure

### Releases and source maps in CI/CD

Need:

- `SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`

### Feature flags

Need:

- the normal Sentry DSN
- the credentials for the actual flag provider

## What Not To Put In The Repo

Do not commit:

- `SENTRY_AUTH_TOKEN`
- private feature flag provider tokens
- CI secrets
- any production-only DSN values if your team prefers env-only configuration

Usually acceptable to expose in frontend/runtime:

- browser DSN/public key
- project slug
- org slug when required by build tooling

## Sentry Views To Actually Use

The custom dashboard alone is not enough. In practice, the team will likely use:

- Issues: error triage
- Trace Explorer: request and dependency performance
- Logs: request-correlated log events
- Releases: deploy correlation
- Cron Monitoring: background jobs
- Replays: frontend debugging if enabled

## Official Docs

These are the main references to use when moving from this sample to the real app:

- Flask integration: https://docs.sentry.io/platforms/python/integrations/flask/
- Python platform docs: https://docs.sentry.io/platforms/python/
- Trace Explorer: https://docs.sentry.io/product/explore/traces/
- Cron Monitoring: https://docs.sentry.io/product/crons/
- OpenFeature integration: https://docs.sentry.io/platforms/python/integrations/openfeature
- Sentry Toolbar: https://docs.sentry.io/product/dev-toolbar/
- Session Replay overview: https://docs.sentry.io/product/explore/session-replay/replay-page-and-filters

## Next Step

When you are ready to instrument the real webapp, use this module as a menu, not a template. Pick the features that match the real architecture, traffic volume, privacy model, and demo goals.
