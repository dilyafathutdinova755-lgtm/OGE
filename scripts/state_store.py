"""Rotation journal: remembers where each stream left off between runs.

Hooks and photos are drawn from a shared/per-group pool without repeats
until the whole pool is used, then the cycle restarts (playbook section 08).
Tail clips and music tracks are small pools and are simply round-robined.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

STATE_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "state.json"

GROUPS = ("english", "russian", "general")


def _default_state() -> dict:
    return {
        "hooks": {g: {"cycle": 0, "used": []} for g in GROUPS},
        "photos": {"cycle": 0, "used": []},
        "tails": {g: 0 for g in GROUPS},
        "music": 0,
    }


class StateStore:
    def __init__(self, path: pathlib.Path = STATE_PATH):
        self.path = path
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = _default_state()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def next_from_pool(self, section: str, group: str | None, pool_size: int) -> int:
        """Return the next index (0-based) into a pool, restarting the cycle when exhausted."""
        bucket = self.data[section][group] if group is not None else self.data[section]
        if len(bucket["used"]) >= pool_size:
            bucket["cycle"] += 1
            bucket["used"] = []
        remaining = [i for i in range(pool_size) if i not in bucket["used"]]
        index = remaining[0]
        bucket["used"].append(index)
        return index

    def next_round_robin(self, section: str, group: str | None, pool_size: int) -> int:
        if pool_size <= 0:
            raise ValueError(f"empty pool for {section}/{group}")
        if group is not None:
            index = self.data[section][group] % pool_size
            self.data[section][group] = (index + 1) % pool_size
        else:
            index = self.data[section] % pool_size
            self.data[section] = (index + 1) % pool_size
        return index
