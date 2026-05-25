#!/usr/bin/env bash
set -euo pipefail

install_root="${DAILY_BRIEF_ROOT:-/opt/daily-open-source-brief}"
service_name="${DAILY_BRIEF_SERVICE_NAME:-daily-open-source-brief}"
collect_service_name="${DAILY_BRIEF_COLLECT_SERVICE_NAME:-daily-open-source-brief-collect}"
rotate_service_name="${DAILY_BRIEF_ROTATE_SERVICE_NAME:-daily-open-source-brief-llm-rotate}"
run_time="${DAILY_BRIEF_RUN_TIME:-06:00:00}"
brief_interval="${DAILY_BRIEF_INTERVAL:-08,11,14,17,20,22:00:00}"
collect_interval="${DAILY_BRIEF_COLLECT_INTERVAL:-*:00:00}"
rotate_interval="${DAILY_BRIEF_ROTATE_INTERVAL:-*:0/30}"
collect_model="${DAILY_BRIEF_COLLECT_MODEL:-gpt-5.4-mini}"
send_model="${DAILY_BRIEF_SEND_MODEL:-gpt-5.5}"
send_reasoning_effort="${DAILY_BRIEF_REASONING_EFFORT:-medium}"
python_bin="${DAILY_BRIEF_PYTHON:-python3}"

usage() {
  cat <<USAGE
Install daily-open-source-brief on Linux.

Options:
  --install-root PATH   Default: ${install_root}
  --service-name NAME   Default: ${service_name}
  --run-time HH:MM:SS   Default: ${run_time}
  --brief-interval CAL  Default: ${brief_interval}
  --collect-interval CAL Default: ${collect_interval}
  --rotate-interval CAL Default: ${rotate_interval}
  --help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) install_root="$2"; shift 2 ;;
    --service-name) service_name="$2"; shift 2 ;;
    --run-time) run_time="$2"; shift 2 ;;
    --brief-interval) brief_interval="$2"; shift 2 ;;
    --collect-interval) collect_interval="$2"; shift 2 ;;
    --rotate-interval) rotate_interval="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/install-linux.sh" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip ca-certificates curl unzip

mkdir -p "${install_root}/data" "${install_root}/logs" "${install_root}/public/archive"
cd "${install_root}"
chmod -R go-w "${install_root}" || true

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created ${install_root}/.env. Fill secrets before enabling real mail/fetch."
fi
chmod 600 .env

"${python_bin}" -m venv .venv
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

cat >"/etc/systemd/system/${service_name}.service" <<EOF
[Unit]
Description=Daily open-source brief
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${install_root}
Environment=HOME=/root
Environment=DAILY_BRIEF_SEND_MODEL=${send_model}
Environment=DAILY_BRIEF_REASONING_EFFORT=${send_reasoning_effort}
EnvironmentFile=${install_root}/.env
EnvironmentFile=-${install_root}/.llm.env
ExecStart=${install_root}/.venv/bin/python -m app.run_daily --send-only
EOF

cat >"/etc/systemd/system/${collect_service_name}.service" <<EOF
[Unit]
Description=Collect daily open-source brief candidates
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${install_root}
Environment=HOME=/root
Environment=DAILY_BRIEF_COLLECT_MODEL=${collect_model}
EnvironmentFile=${install_root}/.env
EnvironmentFile=-${install_root}/.llm.env
ExecStart=${install_root}/.venv/bin/python -m app.run_daily --collect-only
EOF

cat >"/etc/systemd/system/${rotate_service_name}.service" <<EOF
[Unit]
Description=Rotate daily open-source brief LLM provider
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${install_root}
Environment=HOME=/root
EnvironmentFile=${install_root}/.env
ExecStart=${install_root}/.venv/bin/python -m app.rotate_llm_provider --env-out ${install_root}/.llm.env
EOF

cat >"/etc/systemd/system/${rotate_service_name}.timer" <<EOF
[Unit]
Description=Rotate daily open-source brief LLM provider every 30 minutes

[Timer]
OnBootSec=2min
OnCalendar=${rotate_interval}
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

cat >"/etc/systemd/system/${service_name}.timer" <<EOF
[Unit]
Description=Send daily open-source brief

[Timer]
OnCalendar=*-*-* ${brief_interval}
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

cat >"/etc/systemd/system/${collect_service_name}.timer" <<EOF
[Unit]
Description=Collect daily open-source brief candidates hourly

[Timer]
OnCalendar=*-*-* ${collect_interval}
Persistent=true
RandomizedDelaySec=180

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${service_name}.timer"
systemctl enable --now "${collect_service_name}.timer"
systemctl enable --now "${rotate_service_name}.timer"

echo "Installed ${service_name}.timer"
echo "Installed ${collect_service_name}.timer"
echo "Installed ${rotate_service_name}.timer"
echo "Test: systemctl start ${service_name}.service && journalctl -u ${service_name}.service -n 80 --no-pager"
