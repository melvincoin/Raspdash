from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize RaspDash JSONL ride logs")
    parser.add_argument("path", help="Path to ride-YYYY-MM-DD.jsonl")
    args = parser.parse_args()

    counters: dict[str, Counter[str]] = {}
    rows = 0
    moving_rows = 0
    with Path(args.path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            rows += 1
            if (record.get("speed_kmh") or 0) > 0:
                moving_rows += 1
            for key, value in (record.get("candidate_raw") or {}).items():
                counters.setdefault(key, Counter())[str(value)] += 1

    print(f"rows={rows} moving_rows={moving_rows}")
    for key in sorted(counters):
        print(f"\n{key}")
        for value, count in counters[key].most_common():
            print(f"  {value}: {count}")


if __name__ == "__main__":
    main()
