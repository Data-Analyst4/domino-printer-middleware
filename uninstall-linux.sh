#!/usr/bin/env bash
# Thin wrapper — removes systemd service installed by install-linux.sh
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$ROOT_DIR/install-linux.sh" --uninstall "$@"
