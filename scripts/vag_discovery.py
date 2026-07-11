from __future__ import annotations

import argparse
from pathlib import Path

from discovery_common import load_json, now_iso, update_metric, write_json


CATEGORY_TO_METRIC = {
    "dsg_temperature": "dsg_temp",
    "transmission_temperature": "transmission_temp",
    "clutch_temperature": "clutch_temp",
    "oil_temperature": "engine_oil_temp",
    "boost_actual": "charge_pressure_actual",
    "charge_pressure": "charge_pressure_requested",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare VAG read-only discovery state. No scans, no writes.")
    parser.add_argument("--candidates", default="config/vag_candidates.yaml")
    parser.add_argument("--output", default="data/vag_discovery.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    args = parser.parse_args()

    result = {
        "generated_at": now_iso(),
        "candidates_file": args.candidates,
        "requests_sent": 0,
        "status": "prepared_only",
        "notes": [
            "No UDS requests are sent by this script.",
            "Populate config/vag_candidates.yaml manually before any read-only candidate probe.",
            "Security access, coding, adaptations, writes and output tests are forbidden.",
        ],
        "categories": {},
    }
    candidate_text = Path(args.candidates).read_text(encoding="utf-8") if Path(args.candidates).exists() else ""
    for category, metric in CATEGORY_TO_METRIC.items():
        result["categories"][category] = {"metric": metric, "status": "unknown", "configured": category in candidate_text}
        update_metric(Path(args.registry), metric, available=False, status="unknown", value=None)
    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    print("No VAG/UDS requests sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
