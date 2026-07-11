#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a RaspDash ACC distance JSONL log")
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    items = [json.loads(line) for line in args.log.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples = [item for item in items if item.get("type") == "sample"]
    markers = [item for item in items if item.get("type") == "marker"]
    by_did: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        by_did[str(sample.get("did"))].append(sample)

    lines = [f"ACC distance analysis: {args.log.name}", f"Samples: {len(samples)}  Markers: {len(markers)}", ""]
    for did, rows in sorted(by_did.items()):
        statuses = Counter(str(row.get("status")) for row in rows)
        payloads = [bytes.fromhex(row["raw"]) for row in rows if row.get("status") == "ok" and row.get("raw")]
        lines.append(f"DID {did}: statuses={dict(statuses)} unique_payloads={len(set(payloads))}")
        if payloads:
            width = max(map(len, payloads))
            changed = [index for index in range(width) if len({p[index] if index < len(p) else None for p in payloads}) > 1]
            lines.append(f"  changed_bytes={changed or 'none'}")
            lines.append(f"  common={Counter(p.hex(' ').upper() for p in payloads).most_common(8)}")

    lines.append("\nMarkers:")
    for marker in markers:
        marker_ts = parse_ts(marker["ts"])
        nearby = sorted(samples, key=lambda row: abs((parse_ts(row["ts"]) - marker_ts).total_seconds()))[:5]
        lines.append(f"- {marker['ts']} {marker.get('label')}")
        for row in nearby:
            delta = (parse_ts(row["ts"]) - marker_ts).total_seconds()
            lines.append(f"    {delta:+.1f}s DID={row.get('did')} status={row.get('status')} raw={row.get('raw')} context={row.get('context')}")

    output = args.output or args.log.with_name(args.log.stem + "-analysis.txt")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
