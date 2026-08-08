#!/usr/bin/env bash
# =============================================================================
# Domino Printer Middleware — One-click Ubuntu/Debian installer
# =============================================================================
# Installs and enables systemd service:
#   - Domino → port 5003  service: domino-printer-middleware
#
# Usage (from the repo root):
#   chmod +x install-linux.sh
#   ./install-linux.sh
#
# Options:
#   --skip-cloudflare   Do not install cloudflared
#   --no-start          Install unit but do not start service yet
#   --uninstall         Remove service and leave files in place
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIG_ARGS=("$@")
SKIP_CLOUDFLARE=0
NO_START=0
DO_UNINSTALL=0

SERVICE_USER="${SUDO_USER:-$USER}"
if [[ "$SERVICE_USER" == "root" ]]; then
  SERVICE_USER="root"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-cloudflare) SKIP_CLOUDFLARE=1; shift ;;
    --no-start) NO_START=1; shift ;;
    --uninstall) DO_UNINSTALL=1; shift ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run with --help for usage."
      exit 1
      ;;
  esac
done

step() { echo; echo "==> $*"; }
ok()   { echo "  OK: $*"; }
warn() { echo "  WARN: $*" >&2; }
die()  { echo "  ERROR: $*" >&2; exit 1; }

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Re-running with sudo..."
    exec sudo -E bash "$0" "$@"
  fi
}

detect_ubuntu() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"debian"* && "${ID:-}" != "debian" ]]; then
      warn "This installer targets Ubuntu/Debian. Detected: ${PRETTY_NAME:-unknown}"
    else
      ok "OS: ${PRETTY_NAME:-Linux}"
    fi
  fi
}

read_env_value() {
  local file="$1" key="$2" default="$3"
  if [[ -f "$file" ]]; then
    local line
    line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n1 || true)"
    if [[ -n "$line" ]]; then
      echo "${line#*=}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
      return
    fi
  fi
  echo "$default"
}

ensure_config() {
  local example="$1" target="$2"
  if [[ ! -f "$target" && -f "$example" ]]; then
    cp "$example" "$target"
    chown "$SERVICE_USER:$SERVICE_USER" "$target" 2>/dev/null || true
    ok "Created $(basename "$target")"
  fi
}

install_system_packages() {
  step "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    curl \
    ca-certificates \
    build-essential
  ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
}

ensure_python_ok() {
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' \
    || die "Python 3.8+ required"
}

setup_app_venv() {
  local app_dir="$1"
  step "Virtualenv + dependencies"
  mkdir -p "$app_dir/logs"

  if [[ ! -x "$app_dir/.venv/bin/python" ]]; then
    python3 -m venv "$app_dir/.venv"
  fi
  "$app_dir/.venv/bin/python" -m pip install --upgrade pip
  "$app_dir/.venv/bin/pip" install -r "$app_dir/requirements.txt"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$app_dir/.venv" "$app_dir/logs" 2>/dev/null || true
  ok "venv ready at $app_dir/.venv"
}

write_systemd_unit() {
  local service_name="$1"
  local description="$2"
  local work_dir="$3"
  local port="$4"
  local host="$5"
  local env_file="$6"
  local unit_path="/etc/systemd/system/${service_name}.service"

  step "Writing systemd unit: $service_name"

  local env_extra=""
  if [[ -f "$env_file" ]]; then
    env_extra="EnvironmentFile=-${env_file}"
  fi

  cat > "$unit_path" <<EOF
[Unit]
Description=${description}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${work_dir}
Environment=PYTHONUNBUFFERED=1
Environment=HOST=${host}
Environment=PORT=${port}
${env_extra}
ExecStart=${work_dir}/.venv/bin/python ${work_dir}/main.py --host ${host} --port ${port}
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=20
StandardOutput=append:${work_dir}/logs/service-output.log
StandardError=append:${work_dir}/logs/service-error.log

[Install]
WantedBy=multi-user.target
EOF

  ok "$unit_path"
}

wait_health() {
  local port="$1"
  local label="$2"
  local url="http://127.0.0.1:${port}/health"
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      ok "$label health: $url"
      return 0
    fi
    sleep 1
  done
  warn "$label health check timed out at $url — check journalctl -u ${label}"
  return 1
}

install_cloudflared() {
  if [[ "$SKIP_CLOUDFLARE" -eq 1 ]]; then
    warn "Skipping cloudflared (--skip-cloudflare)"
    return
  fi
  step "cloudflared (optional public HTTPS)"
  if command -v cloudflared >/dev/null 2>&1; then
    ok "cloudflared already installed: $(command -v cloudflared)"
    return
  fi

  local arch
  arch="$(dpkg --print-architecture)"
  local deb_url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb"
  local tmp_deb
  tmp_deb="$(mktemp /tmp/cloudflared.XXXXXX.deb)"
  if curl -fsSL -o "$tmp_deb" "$deb_url"; then
    dpkg -i "$tmp_deb" || apt-get install -f -y
    rm -f "$tmp_deb"
    ok "cloudflared installed"
    echo "  Next (optional, once per site):"
    echo "    cloudflared tunnel login"
    echo "    cloudflared tunnel create <name>"
    echo "    cloudflared tunnel route dns <name> <hostname>"
    echo "    Edit ~/.cloudflared/config.yml then: sudo cloudflared service install"
  else
    rm -f "$tmp_deb"
    warn "Could not download cloudflared — install manually if you need a public tunnel"
  fi
}

enable_and_start() {
  local service_name="$1"
  local port="$2"
  systemctl daemon-reload
  systemctl enable "$service_name"
  if [[ "$NO_START" -eq 1 ]]; then
    ok "Enabled $service_name (not started --no-start)"
    return
  fi
  systemctl restart "$service_name"
  wait_health "$port" "$service_name" || true
}

uninstall_services() {
  step "Uninstalling systemd services"
  local name="domino-printer-middleware"
  if systemctl list-unit-files "${name}.service" >/dev/null 2>&1; then
    systemctl stop "$name" 2>/dev/null || true
    systemctl disable "$name" 2>/dev/null || true
    rm -f "/etc/systemd/system/${name}.service"
    ok "Removed $name"
  fi
  systemctl daemon-reload
  echo
  echo "Service removed. App files and virtualenv were left in place."
  echo "Delete the repo folder manually if you want a full wipe."
}

install_domino() {
  local app_dir="$ROOT_DIR"
  local site_env="$app_dir/config/site.env"
  ensure_config "$app_dir/config/site.env.example" "$site_env"
  ensure_config "$app_dir/config/printers.json.example" "$app_dir/config/printers.json"
  mkdir -p "$app_dir/logs"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$app_dir/config" "$app_dir/logs" 2>/dev/null || true

  setup_app_venv "$app_dir"

  local port host
  port="$(read_env_value "$site_env" PORT 5003)"
  host="$(read_env_value "$site_env" HOST 0.0.0.0)"

  write_systemd_unit \
    "domino-printer-middleware" \
    "Domino Printer Middleware" \
    "$app_dir" \
    "$port" \
    "$host" \
    "$site_env"
  enable_and_start "domino-printer-middleware" "$port"
}

print_summary() {
  echo
  echo "============================================================"
  echo "  Domino Printer Middleware — Linux install complete"
  echo "============================================================"
  echo "  Repo:     $ROOT_DIR"
  echo "  Run as:   $SERVICE_USER"
  echo
  echo "  Domino:  http://127.0.0.1:$(read_env_value "$ROOT_DIR/config/site.env" PORT 5003)/health"
  echo "           sudo systemctl status domino-printer-middleware"
  echo
  echo "  Edit printer IP before go-live:"
  echo "    nano $ROOT_DIR/config/printers.json"
  echo
  echo "  Uninstall service:"
  echo "    sudo ./install-linux.sh --uninstall"
  echo "============================================================"
}

echo
echo "============================================================"
echo "  Domino Printer Middleware — Ubuntu one-click installer"
echo "============================================================"

need_root "${ORIG_ARGS[@]}"

if [[ "$DO_UNINSTALL" -eq 1 ]]; then
  uninstall_services
  exit 0
fi

detect_ubuntu
install_system_packages
ensure_python_ok
install_domino
install_cloudflared
print_summary
