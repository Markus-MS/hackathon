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
host="${FLAGFARM_HOST:-127.0.0.1}"
port="${FLAGFARM_PORT:-8080}"

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
Environment=FLAGFARM_HOST=${host}
Environment=FLAGFARM_PORT=${port}
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
