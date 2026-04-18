#!/usr/bin/env bash
set -euo pipefail

MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${MODULE_DIR}/../.." && pwd)"
IMAGE_TAG="${FLAGFARM_SOLVER_IMAGE:-flagfarm-solver:local}"

docker build -f "${MODULE_DIR}/solver.Dockerfile" -t "${IMAGE_TAG}" "${REPO_ROOT}"
