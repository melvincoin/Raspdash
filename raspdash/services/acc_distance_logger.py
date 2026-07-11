from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACC_DIDS = ("102E", "1011", "1012", "1065", "1880")


class AccDistanceLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._index = 0
        self._failures: dict[str, int] = {}
        self._blocked: set[str] = set()

    def start_ride(self) -> None:
        with self._lock:
            if self._path is not None:
                return
            self.log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            self._path = self.log_dir / f"acc-distance-{stamp}.jsonl"
            self._index = 0
            self._failures.clear()
            self._blocked.clear()

    def stop_ride(self) -> None:
        with self._lock:
            self._path = None

    def next_did(self) -> str | None:
        with self._lock:
            candidates = [did for did in ACC_DIDS if did not in self._blocked]
            if not candidates or self._path is None:
                return None
            did = candidates[self._index % len(candidates)]
            self._index += 1
            return did

    def record(self, did: str, payload: list[int] | None, status: str, context: dict[str, Any]) -> None:
        with self._lock:
            if self._path is None:
                return
            if status == "ok":
                self._failures.pop(did, None)
            elif status in {"unsupported", "timeout"}:
                self._failures[did] = self._failures.get(did, 0) + 1
                if self._failures[did] >= 3:
                    self._blocked.add(did)
            self._write({
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "sample",
                "module": "13",
                "did": did,
                "raw": " ".join(f"{byte:02X}" for byte in payload) if payload else "",
                "status": status,
                "context": context,
            })

    def marker(self, label: str) -> bool:
        with self._lock:
            if self._path is None:
                return False
            self._write({"ts": datetime.now(timezone.utc).isoformat(), "type": "marker", "label": label})
            return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"active": self._path is not None, "file": str(self._path or ""), "blocked": sorted(self._blocked)}

    def _write(self, item: dict[str, Any]) -> None:
        if self._path is None:
            return
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, separators=(",", ":")) + "\n")
        except OSError:
            pass
