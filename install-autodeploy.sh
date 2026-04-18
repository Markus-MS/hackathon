#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this on the server with sudo: sudo ./install-autodeploy.sh"
  exit 1
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_name="${APP_NAME:-flagfarm}"
branch="${DEPLOY_BRANCH:-$(git -C "$repo_dir" branch --show-current 2>/dev/null || true)}"
branch="${branch:-master}"
run_user="${DEPLOY_USER:-$(id -un)}"
run_group="${DEPLOY_GROUP:-$(id -gn "$run_user")}"
host="${CTF_ARENA_HOST:-${FLAGFARM_HOST:-127.0.0.1}}"
port="${CTF_ARENA_PORT:-${FLAGFARM_PORT:-8080}}"

find_uv() {
  local candidate

  for candidate in \
    /usr/local/bin/uv \
    /usr/bin/uv \
    /root/.local/bin/uv \
    "${HOME:-/nonexistent}/.local/bin/uv"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if candidate="$(command -v uv 2>/dev/null)"; then
    printf '%s\n' "$candidate"
    return 0
  fi

  return 1
}

ensure_uv() {
  local uv_bin

  if uv_bin="$(find_uv)"; then
    if [[ "$uv_bin" != "/usr/local/bin/uv" && ! -x /usr/local/bin/uv ]]; then
      install -m 0755 "$uv_bin" /usr/local/bin/uv
      uv_bin="/usr/local/bin/uv"
    fi
    printf '%s\n' "$uv_bin"
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    echo "uv is not installed and curl is unavailable; install uv first." >&2
    exit 1
  fi

  echo "Installing uv into /usr/local/bin" >&2
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh >&2
  find_uv
}

uv_bin="$(ensure_uv)"
uv_dir="$(dirname "$uv_bin")"
service_path="$uv_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

cat >"/etc/systemd/system/${app_name}.service" <<EOF
[Unit]
Description=FlagFarm dev server
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=${run_user}
Group=${run_group}
WorkingDirectory=${repo_dir}
EnvironmentFile=-${repo_dir}/.env
Environment=PATH=${service_path}
Environment=CTF_ARENA_HOST=${host}
Environment=CTF_ARENA_PORT=${port}
ExecStart=${repo_dir}/serve.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >"/etc/systemd/system/${app_name}-autodeploy.service" <<EOF
[Unit]
Description=Pull and redeploy FlagFarm from ${branch}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${repo_dir}
Environment=DEPLOY_BRANCH=${branch}
Environment=APP_SERVICE=${app_name}.service
ExecStart=${repo_dir}/redeploy.sh
EOF

cat >"/etc/systemd/system/${app_name}-autodeploy.timer" <<EOF
[Unit]
Description=Poll git and redeploy FlagFarm

[Timer]
OnBootSec=20s
OnUnitActiveSec=30s
Unit=${app_name}-autodeploy.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${app_name}.service"
systemctl enable --now "${app_name}-autodeploy.timer"

echo "Installed ${app_name}.service and ${app_name}-autodeploy.timer"
echo "Tracking ${branch} from ${repo_dir}"
echo "Logs: journalctl -u ${app_name}.service -u ${app_name}-autodeploy.service -f"
