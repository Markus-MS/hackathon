# FlagFarm

FlagFarm is a Flask MVP for running a weekly CTF evaluation across four LLMs under the same budget contract, then publishing a public leaderboard and solve matrix.

## What Is In This Repo

- A modular Flask app factory in `flagfarm/`
- SQLite persistence with an auditable `v_competition_scores` view
- Public landing page with:
  - weekly leaderboard
  - model x challenge solve matrix
  - recent-week archive
- Admin backend with:
  - single-admin login
  - weekly CTF creation
  - CTFd challenge sync
  - per-model CTF account provisioning
  - competition start control
- Central pricing from one rate table in [flagfarm/data/model_rates.json](/root/hackathon/flagfarm/data/model_rates.json)
- Optional Sentry wiring if `SENTRY_DSN` is set
- A seeded demo flow so the app can be exercised immediately

## Architecture

The app is intentionally split into small modules instead of a single `app.py`.

- [flagfarm/__init__.py](/root/hackathon/flagfarm/__init__.py) builds the app and registers blueprints.
- [flagfarm/db.py](/root/hackathon/flagfarm/db.py) owns SQLite setup and reference-data seeding.
- [flagfarm/schema.sql](/root/hackathon/flagfarm/schema.sql) defines the tables and the leaderboard view.
- [flagfarm/services/ctf_service.py](/root/hackathon/flagfarm/services/ctf_service.py) handles weekly CTFs, challenges, models, and accounts.
- [flagfarm/services/ctfd.py](/root/hackathon/flagfarm/services/ctfd.py) is the CTFd adapter.
- [flagfarm/services/competition.py](/root/hackathon/flagfarm/services/competition.py) owns run creation and the four-model in-process runner.
- [flagfarm/services/leaderboard.py](/root/hackathon/flagfarm/services/leaderboard.py) builds the ranked table and public matrix.
- [flagfarm/telemetry.py](/root/hackathon/flagfarm/telemetry.py) centralizes optional Sentry setup and basic scrubbing.

## Run It

The Python entrypoints use `uv` inline script metadata, per repo instructions.

1. Seed demo data:

```sh
./seed_demo.py
```

2. Start the app:

```sh
./serve.py
```

3. Open `http://127.0.0.1:5000`

Admin defaults:

- username: `admin`
- password: `flagfarm-admin`

Override them with:

- `FLAGFARM_ADMIN_USERNAME`
- `FLAGFARM_ADMIN_PASSWORD`
- `FLAGFARM_SECRET_KEY`
- `SENTRY_DSN`

## Notes

- The bundled rate card is meant to be the single source of truth for cost calculations in this MVP. Update it before relying on production cost numbers.
- The current runner uses a simulated backend so the platform, scoreboard, budgets, and observability shape can be exercised without live model-provider credentials.

## Server Access

```sh
ssh root@116.202.9.5
```

or:

```sshconfig
Host hackathon
    HostName 116.202.9.5
    PreferredAuthentications publickey
    User root
    Port 22
```
