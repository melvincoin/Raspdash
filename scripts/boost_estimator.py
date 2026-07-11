from __future__ import annotations

import argparse
from pathlib import Path

from discovery_common import load_json, now_iso, update_metric, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate boost from MAP and BARO probe results.")
    parser.add_argument("--value-probe", default="data/value_probe.json")
    parser.add_argument("--output", default="data/boost_estimate.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--baro-fallback-kpa", type=float, default=101.3)
    return parser.parse_args()


def value(data: dict, key: str) -> float | None:
    item = data.get("values", {}).get(key, {})
    raw = item.get("value")
    return raw if isinstance(raw, (int, float)) else None


def main() -> int:
    args = parse_args()
    probe = load_json(Path(args.value_probe), {"values": {}})
    map_kpa = value(probe, "manifold_absolute_pressure")
    baro_kpa = value(probe, "barometric_pressure")
    used_fallback = False
    if map_kpa is not None and baro_kpa is None:
        baro_kpa = args.baro_fallback_kpa
        used_fallback = True

    if map_kpa is None:
        status = "unavailable"
        boost_kpa = None
        boost_bar = None
    else:
        status = "estimated_fallback_baro" if used_fallback else "estimated"
        boost_kpa = map_kpa - float(baro_kpa)
        boost_bar = boost_kpa / 100

    result = {
        "generated_at": now_iso(),
        "map_kpa": map_kpa,
        "baro_kpa": baro_kpa,
        "baro_fallback_used": used_fallback,
        "boost_estimated_kpa": boost_kpa,
        "boost_estimated_bar": boost_bar,
        "status": status,
        "raw_sources": ["manifold_absolute_pressure", "barometric_pressure"],
    }

    update_metric(
        Path(args.registry),
        "boost_estimated_kpa",
        available=boost_kpa is not None,
        status=status,
        value=boost_kpa,
        confidence=0.45 if used_fallback else 0.55,
    )
    update_metric(
        Path(args.registry),
        "boost_estimated_bar",
        available=boost_bar is not None,
        status=status,
        value=boost_bar,
        confidence=0.45 if used_fallback else 0.55,
    )
    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    print(f"Updated {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
