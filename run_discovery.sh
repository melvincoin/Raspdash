#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-/opt/raspdash/.venv/bin/python}"
BAUDRATE="${BAUDRATE:-115200}"
PROTOCOL="${PROTOCOL:-6}"
HEADER="${HEADER:-7DF}"
SAMPLES="${SAMPLES:-6}"
RUN_UDS="${RUN_UDS:-0}"

mkdir -p data reports logs
exec > >(tee "reports/run_discovery.log") 2>&1

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$*"
}

if systemctl is-active --quiet raspdash.service 2>/dev/null; then
  log "Stopping raspdash.service for exclusive adapter access"
  sudo systemctl stop raspdash.service
  RESTART_RASPDASH=1
else
  RESTART_RASPDASH=0
fi

cleanup() {
  if [[ "${RESTART_RASPDASH}" == "1" ]]; then
    log "Starting raspdash.service"
    sudo systemctl start raspdash.service || true
  fi
}
trap cleanup EXIT

log "Detecting USB adapter"
if ! "${PYTHON}" scripts/detect_adapter.py --output data/adapter_detection.json | tee reports/adapter_detection.txt; then
  echo "No /dev/ttyUSB* or /dev/ttyACM* adapter detected." >&2
  exit 1
fi

PORT="$("${PYTHON}" - <<'PY'
import json
data=json.load(open("data/adapter_detection.json"))
print(data["adapters"][0]["device"])
PY
)"
log "Using adapter ${PORT}"

log "Adapter inventory"
"${PYTHON}" scripts/adapter_inventory.py --port "${PORT}" --baudrate "${BAUDRATE}" --protocol "${PROTOCOL}" --header "${HEADER}" --json-output data/adapter_inventory.json --report reports/adapter_inventory.md

log "PID inventory"
"${PYTHON}" scripts/pid_inventory.py --port "${PORT}" --baudrate "${BAUDRATE}" --protocol "${PROTOCOL}" --header "${HEADER}" --output data/pid_inventory.json

log "Metric discovery"
"${PYTHON}" scripts/metric_discovery.py --port "${PORT}" --baudrate "${BAUDRATE}" --protocol "${PROTOCOL}" --header "${HEADER}" --pid-inventory data/pid_inventory.json --output data/metric_discovery.json --registry data/metric_registry.json --samples "${SAMPLES}"

log "Boost estimate"
"${PYTHON}" scripts/boost_estimator.py --value-probe data/metric_discovery.json --output data/boost_estimate.json --registry data/metric_registry.json

log "VAG discovery preparation"
"${PYTHON}" scripts/vag_discovery.py --candidates config/vag_candidates.yaml --output data/vag_discovery.json --registry data/metric_registry.json

if [[ "${RUN_UDS}" == "1" ]]; then
  log "UDS ReadDataByIdentifier probe"
  "${PYTHON}" scripts/uds_probe.py --port "${PORT}" --baudrate "${BAUDRATE}" --protocol "${PROTOCOL}" --ecus config/uds_ecus.yaml --candidates config/vag_dids_candidates.yaml --output data/uds_probe.json --registry data/metric_registry.json --execute
else
  log "UDS probe prepared only"
  "${PYTHON}" scripts/uds_probe.py --port "${PORT}" --baudrate "${BAUDRATE}" --protocol "${PROTOCOL}" --ecus config/uds_ecus.yaml --candidates config/vag_dids_candidates.yaml --output data/uds_probe.json --registry data/metric_registry.json
fi

log "Report"
"${PYTHON}" scripts/discovery_report.py --registry data/metric_registry.json --output reports/discovery_report.md

log "Done"
printf '\nReports:\n'
printf '  reports/adapter_inventory.md\n'
printf '  reports/discovery_report.md\n'
printf '\nData:\n'
printf '  data/adapter_detection.json\n'
printf '  data/pid_inventory.json\n'
printf '  data/metric_discovery.json\n'
printf '  data/metric_registry.json\n'
printf '  data/uds_probe.json\n'
