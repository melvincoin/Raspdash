#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
LOG=/tmp/raspdash-kiosk.log
log() {
  printf '%s start-kiosk: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

log "kiosk start"
xsetroot -solid black || true
log "x11 black background set"
xset -dpms || true
xset s off || true
xset s noblank || true
(while sleep 10; do
  vcgencmd display_power 1 >/dev/null 2>&1 || true
  xset dpms force on >/dev/null 2>&1 || true
  xset -dpms >/dev/null 2>&1 || true
  xset s off >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
done) &
log "hdmi keepalive started pid=$!"
unclutter -idle 0.1 -root &
openbox-session &
python3 /opt/raspdash/scripts/black-cover.py --timeout 30 >> "$LOG" 2>&1 &
log "cover started launcher_pid=$!"

if command -v surf >/dev/null 2>&1; then
  mkdir -p "${HOME}/.surf"
  cat > "${HOME}/.surf/styles.css" <<'CSS'
html, body {
  background: #000000 !important;
}
CSS

  export WEBKIT_DISABLE_COMPOSITING_MODE=1
  log "surf started"
  exec surf -F -C "${HOME}/.surf/styles.css" http://127.0.0.1:5000/
fi

mkdir -p /tmp/raspdash-kiosk-profile

log "chromium fallback started"
exec chromium \
  --no-memcheck \
  --kiosk \
  --user-data-dir=/tmp/raspdash-kiosk-profile \
  --default-background-color=000000 \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-dev-shm-usage \
  --autoplay-policy=no-user-gesture-required \
  http://127.0.0.1:5000/
