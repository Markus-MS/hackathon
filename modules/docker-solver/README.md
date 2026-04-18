# Docker Solver Module

This module builds the local container image used by https://ctfarena.live/ solver runs.

```sh
./modules/docker-solver/build_image.sh
```

The image tag defaults to `ctfarena-solver:local`. Override it with:

```sh
CTF_ARENA_SOLVER_IMAGE=registry.example.com/ctfarena-solver:dev ./modules/docker-solver/build_image.sh
```
