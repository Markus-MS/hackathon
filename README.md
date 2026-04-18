# https://ctfarena.live/

https://ctfarena.live/ is a Flask MVP for running a weekly CTF evaluation across one or more configured LLMs under the same budget contract, then publishing a public leaderboard and solve matrix.

## What Is In This Repo

- A modular Flask app factory in `ctfarena/`
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
- Central pricing from one rate table in [ctfarena/data/model_rates.json](ctfarena/data/model_rates.json)
- Optional Sentry wiring if `SENTRY_DSN` is set
- Docker-isolated solver runs that verify candidate flags through CTFd before scoring

## Architecture

The app is intentionally split into a small core package plus standalone modules instead of a single `app.py`.

- [ctfarena/__init__.py](ctfarena/__init__.py) builds the app and registers blueprints.
- [ctfarena/db.py](ctfarena/db.py) owns SQLite setup and reference-data seeding.
- [ctfarena/schema.sql](ctfarena/schema.sql) defines the tables and the leaderboard view.
- [ctfarena/services/ctf_service.py](ctfarena/services/ctf_service.py) handles weekly CTFs, challenges, models, and accounts.
- [ctfarena/services/ctfd.py](ctfarena/services/ctfd.py) is the CTFd adapter.
- [ctfarena/services/competition.py](ctfarena/services/competition.py) owns run creation and the Docker-backed model runner.
- [ctfarena/services/leaderboard.py](ctfarena/services/leaderboard.py) builds the ranked table and public matrix.
- [ctfarena/telemetry.py](ctfarena/telemetry.py) centralizes optional Sentry setup and basic scrubbing.
- [modules/frontend](modules/frontend) owns the public https://ctfarena.live/ frontend and shared admin UI templates/theme.
- [modules/ctfarena](modules/ctfarena) provides a runnable module entrypoint for the current https://ctfarena.live/ app.
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

You can also start the same app through the module entrypoint:

```sh
./modules/ctfarena/server.py
```

3. Open `http://127.0.0.1:8080`

4. In `Admin`, configure:

- provider API keys
- Docker image/network settings
- max parallel solver runs, which defaults to `1` for test runs
- the model profiles you want to run
- CTFd URL and auth secret
- one CTFd API token/account per model you want to run

Then sync challenges and start the competition.

Admin defaults:

- username: `admin`
- password: `ctfarena-admin`

Override them with:

- `CTF_ARENA_ADMIN_USERNAME`
- `CTF_ARENA_ADMIN_PASSWORD`
- `CTF_ARENA_SECRET_KEY`
- `SENTRY_DSN`

## Dev Auto Deploy

On the server, from this repo:

```sh
sudo ./install-autodeploy.sh
```

This installs:

- `flagfarm.service`, which runs `./serve.py`
- `flagfarm-autodeploy.timer`, which checks git every 30 seconds

When the tracked branch changes, it runs `./redeploy.sh`, fast-forwards the repo, rebuilds the solver Docker image, and restarts `flagfarm.service`.

The installer tracks the currently checked-out branch by default. To force `master`:

```sh
sudo env DEPLOY_BRANCH=master ./install-autodeploy.sh
```

Useful commands:

```sh
systemctl status flagfarm.service
systemctl status flagfarm-autodeploy.timer
journalctl -u flagfarm.service -u flagfarm-autodeploy.service -f
```

## Notes

- The bundled rate card is meant to be the single source of truth for cost calculations in this MVP. Update it before relying on production cost numbers.
- There is no simulated scoring path. A challenge is marked solved only after a Docker-isolated solver proposes a candidate flag and CTFd accepts that submission.
- The default solver image is `ctfarena-solver:local`; change it in the admin settings if you have a hardened CTF image with additional tools.

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
