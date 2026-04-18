# Docker Solver Module

This module builds the local container image used by FlagFarm solver runs.

```sh
./modules/docker-solver/build_image.sh
```

The image tag defaults to `flagfarm-solver:local`. Override it with:

```sh
FLAGFARM_SOLVER_IMAGE=registry.example.com/flagfarm-solver:dev ./modules/docker-solver/build_image.sh
```
