# CTFArena Module

This module entrypoint runs the current CTFArena app from the repository root.

It uses the same Flask app factory, SQLite instance database, Docker solver image,
admin UI, model roster, CTFd sync, and competition runner as `serve.py`.

## Run

```sh
./modules/ctfarena/server.py
```

Defaults:

- URL: `http://127.0.0.1:8080`
- Admin username: `admin`
- Admin password: `ctfarena-admin`

Override the host or port with:

```sh
FLAGFARM_HOST=0.0.0.0 FLAGFARM_PORT=8081 ./modules/ctfarena/server.py
```

Build the solver image before starting competitions:

```sh
./modules/docker-solver/build_image.sh
```
