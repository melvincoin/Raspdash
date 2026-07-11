#!/usr/bin/env bash
set -euo pipefail

SPLASH_DIR="/opt/raspdash/raspdash/static/uploads/splash"
CONFIG="/opt/raspdash/data/config.json"

image="$(
python3 - <<'PY'
import json
from pathlib import Path

splash_dir = Path("/opt/raspdash/raspdash/static/uploads/splash")
config_path = Path("/opt/raspdash/data/config.json")
name = "boot-splash.jpg"
if config_path.exists():
    try:
        name = json.loads(config_path.read_text(encoding="utf-8")).get("display", {}).get("splash", name)
    except (OSError, json.JSONDecodeError):
        pass

candidate = splash_dir / name
if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png"} or not candidate.exists():
    for path in sorted(splash_dir.iterdir()):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            candidate = path
            break

print(candidate)
PY
)"

if [[ ! -e /dev/fb0 || ! -f "${image}" || ! -x /usr/bin/fbi ]]; then
  exit 0
fi

setterm -cursor off >/dev/tty1 2>/dev/null || true
exec /usr/bin/fbi -T 1 -d /dev/fb0 -noverbose -a "${image}"
