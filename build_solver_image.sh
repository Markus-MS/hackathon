#!/usr/bin/env bash
set -euo pipefail

docker build -f docker/solver.Dockerfile -t flagfarm-solver:local .
