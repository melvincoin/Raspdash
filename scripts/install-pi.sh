#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash ./scripts/install-pi.sh" >&2
  exit 1
fi

install -d /opt/raspdash

TARGET_USER="${SUDO_USER:-}"
if [[ -z "${TARGET_USER}" || "${TARGET_USER}" == "root" ]]; then
  TARGET_USER="$(stat -c '%U' /opt/raspdash)"
fi
if ! id "${TARGET_USER}" >/dev/null 2>&1; then
  echo "Cannot determine a non-root dashboard user. Run with sudo from the target user account." >&2
  exit 1
fi
TARGET_GROUP="$(id -gn "${TARGET_USER}")"
TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"

render_unit() {
  local source="$1"
  local target="$2"
  sed \
    -e "s#__RASPDASH_USER__#${TARGET_USER}#g" \
    -e "s#__RASPDASH_GROUP__#${TARGET_GROUP}#g" \
    -e "s#__RASPDASH_HOME__#${TARGET_HOME}#g" \
    "${source}" >"${target}"
  chmod 0644 "${target}"
}

render_unit scripts/services/raspdash.service /etc/systemd/system/raspdash.service
render_unit scripts/services/raspdash-kiosk.service /etc/systemd/system/raspdash-kiosk.service
install -m 0644 scripts/services/raspdash-splash.service /etc/systemd/system/raspdash-splash.service
if grep -q '"bluetooth_mac": *"[^"]' /opt/raspdash/data/config.json 2>/dev/null; then
  ELM327_MAC="$(python3 - <<'PY'
import json
from pathlib import Path
config = json.loads(Path("/opt/raspdash/data/config.json").read_text(encoding="utf-8"))
print(config.get("obd", {}).get("elm327", {}).get("bluetooth_mac", ""))
PY
)"
else
  ELM327_MAC=""
fi
if [[ -n "${ELM327_MAC}" ]]; then
  sed "s#__ELM327_MAC__#${ELM327_MAC}#g" scripts/services/raspdash-rfcomm.service >/etc/systemd/system/raspdash-rfcomm.service
  chmod 0644 /etc/systemd/system/raspdash-rfcomm.service
fi
chmod +x /opt/raspdash/scripts/start-kiosk.sh
chmod +x /opt/raspdash/scripts/start-splash.sh

install -d /etc/X11
cat >/etc/X11/Xwrapper.config <<'XWRAPPER'
allowed_users=anybody
needs_root_rights=yes
XWRAPPER

cat >/etc/hostname <<'HOSTNAME'
dashboard
HOSTNAME

if ! grep -q "127.0.1.1 dashboard" /etc/hosts; then
  echo "127.0.1.1 dashboard" >>/etc/hosts
fi

systemctl daemon-reload
systemctl enable avahi-daemon
systemctl enable raspdash.service
if [[ -n "${ELM327_MAC}" ]]; then
  systemctl enable raspdash-rfcomm.service
fi
systemctl enable raspdash-kiosk.service
systemctl enable raspdash-splash.service

echo "RaspDash services installed. Reboot to start kiosk mode."
