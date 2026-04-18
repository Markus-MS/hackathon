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
  - provider API key and Docker runner configuration
  - live run/challenge monitoring with recent events, costs, and errors
  - competition start control
- Central pricing from one rate table in [flagfarm/data/model_rates.json](flagfarm/data/model_rates.json)
- Optional Sentry wiring if `SENTRY_DSN` is set
- Docker-isolated solver runs that verify candidate flags through CTFd before scoring

## Architecture

The app is intentionally split into a small core package plus standalone modules instead of a single `app.py`.

- [flagfarm/__init__.py](flagfarm/__init__.py) builds the app and registers blueprints.
- [flagfarm/db.py](flagfarm/db.py) owns SQLite setup and reference-data seeding.
- [flagfarm/schema.sql](flagfarm/schema.sql) defines the tables and the leaderboard view.
- [flagfarm/services/ctf_service.py](flagfarm/services/ctf_service.py) handles weekly CTFs, challenges, models, and accounts.
- [flagfarm/services/ctfd.py](flagfarm/services/ctfd.py) is the CTFd adapter.
- [flagfarm/services/competition.py](flagfarm/services/competition.py) owns run creation and the Docker-backed four-model runner.
- [flagfarm/services/leaderboard.py](flagfarm/services/leaderboard.py) builds the ranked table and public matrix.
- [flagfarm/telemetry.py](flagfarm/telemetry.py) centralizes optional Sentry setup and basic scrubbing.
- [modules/frontend](modules/frontend) owns the public FlagFarm frontend.
- [modules/docker-solver](modules/docker-solver) owns the local solver image build.
- [modules/sentry-flask-starter](modules/sentry-flask-starter) keeps the standalone Sentry demo app.
- [modules/live-terminal](modules/live-terminal) keeps the standalone live terminal demo.

## Run It

The Python entrypoints use `uv` inline script metadata, per repo instructions.

1. Build the local solver image:

```sh
./modules/docker-solver/build_image.sh
```

2. Start the app:

```sh
./serve.py
```

3. Open `http://127.0.0.1:8080`

4. In `Admin`, configure:

- provider API keys
- Docker image/network settings
- the four model profiles
- CTFd URL and auth secret
- one account per model

Then sync challenges and start the competition.

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
- There is no simulated scoring path. A challenge is marked solved only after a Docker-isolated solver proposes a candidate flag and CTFd accepts that submission.
- The default solver image is `flagfarm-solver:local`; change it in the admin settings if you have a hardened CTF image with additional tools.

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
