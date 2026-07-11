from __future__ import annotations

import argparse
from pathlib import Path

from discovery_common import load_json, now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate markdown discovery report.")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--output", default="reports/discovery_report.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_json(Path(args.registry), {"metrics": {}})
    lines = [
        "# Discovery Report",
        "",
        f"Generated: {now_iso()}",
        "",
        "| Value | Source | Works | Raw Response | Confidence |",
        "|---|---|---:|---|---:|",
    ]
    for key in sorted(registry.get("metrics", {})):
        item = registry["metrics"][key]
        works = "yes" if item.get("available") else "no"
        raw = str(item.get("raw_response") or item.get("status") or "").replace("\n", " ").replace("|", "\\|")
        confidence = item.get("confidence", "")
        lines.append(
            f"| {item.get('display_name', key)} (`{key}`) | {item.get('source', '')} | {works} | {raw} | {confidence} |"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
