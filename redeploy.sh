#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

remote="${DEPLOY_REMOTE:-origin}"
branch="${DEPLOY_BRANCH:-$(git branch --show-current 2>/dev/null || true)}"
branch="${branch:-master}"
service="${APP_SERVICE:-flagfarm.service}"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

log "Checking $remote/$branch"
git fetch --quiet "$remote" "$branch"

before="$(git rev-parse HEAD)"
after="$(git rev-parse "$remote/$branch")"

if [[ "$before" == "$after" ]]; then
  log "Already up to date"
  exit 0
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$branch" ]]; then
  log "Switching from $current_branch to $branch"
  git checkout "$branch"
fi

log "Fast-forwarding to $remote/$branch"
git merge --ff-only "$remote/$branch"

log "Building solver image"
./build_solver_image.sh

if command -v systemctl >/dev/null 2>&1 &&
  [[ -d /run/systemd/system ]] &&
  systemctl list-unit-files --no-legend "$service" 2>/dev/null | grep -q "$service"; then
  log "Restarting $service"
  systemctl restart "$service"
else
  log "Updated code, but $service was not found; restart the app manually"
fi
