#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

remote="${DEPLOY_REMOTE:-origin}"
branch="${DEPLOY_BRANCH:-$(git branch --show-current 2>/dev/null || true)}"
branch="${branch:-master}"
service="${APP_SERVICE:-flagfarm.service}"
service_dropin_changed=0

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

find_uv() {
  local candidate

  if candidate="$(command -v uv 2>/dev/null)"; then
    printf '%s\n' "$candidate"
    return 0
  fi

  for candidate in \
    /root/.local/bin/uv \
    "$HOME/.local/bin/uv" \
    /usr/local/bin/uv \
    /usr/bin/uv; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

systemd_has_service() {
  command -v systemctl >/dev/null 2>&1 &&
    [[ -d /run/systemd/system ]] &&
    systemctl list-unit-files --no-legend "$service" 2>/dev/null | grep -q "$service"
}

configure_service_uv_path() {
  local uv_bin uv_dir service_path dropin_dir dropin tmp current

  if ! uv_bin="$(find_uv)"; then
    log "uv was not found; $service may fail to start if it uses uv"
    return 0
  fi

  uv_dir="$(dirname "$uv_bin")"
  service_path="$uv_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  dropin_dir="/etc/systemd/system/$service.d"
  dropin="$dropin_dir/10-uv-path.conf"

  if [[ "$(id -u)" != "0" ]]; then
    log "Found uv at $uv_bin, but not running as root; skipping $service PATH drop-in"
    return 0
  fi

  current="[Service]
Environment=\"PATH=$service_path\"
"

  if [[ -f "$dropin" ]] && cmp -s "$dropin" <(printf '%s' "$current"); then
    log "$service PATH already includes $uv_dir"
    return 0
  fi

  log "Configuring $service PATH to include $uv_dir"
  mkdir -p "$dropin_dir"
  tmp="$(mktemp "$dropin.XXXXXX")"
  printf '%s' "$current" >"$tmp"
  mv "$tmp" "$dropin"
  systemctl daemon-reload
  service_dropin_changed=1
}

restart_service() {
  configure_service_uv_path
  log "Restarting $service"
  systemctl restart "$service"
}

log "Checking $remote/$branch"
git fetch --quiet "$remote" "$branch"

before="$(git rev-parse HEAD)"
after="$(git rev-parse "$remote/$branch")"

if [[ "$before" == "$after" ]]; then
  log "Already up to date"
  if systemd_has_service; then
    configure_service_uv_path
    if [[ "$service_dropin_changed" == "1" ]] || ! systemctl is-active --quiet "$service"; then
      log "Restarting $service"
      systemctl restart "$service"
    fi
  fi
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

if systemd_has_service; then
  restart_service
else
  log "Updated code, but $service was not found; restart the app manually"
fi
