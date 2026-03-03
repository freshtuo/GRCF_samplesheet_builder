# runtime_config.py
# UI runtime environment config (flowcell, lanes, storage folders)
# 

from __future__ import annotations
from typing import Optional

import json
from dataclasses import dataclass, asdict
from pathlib import Path

# ---- defaults ----
DEFAULT_READ1 = 101
DEFAULT_READ2 = 101

FLOWCELL_PRESETS = {
    "1.5B": {
        "n_lanes": 2,
        "lane_capacity_m": 750,   # 1.5B / 2 lanes
    },
    "10B": {
        "n_lanes": 8,
        "lane_capacity_m": 1250,  # 10B / 8 lanes
    },
    "25B": {
        "n_lanes": 8,
        "lane_capacity_m": 3125,  # 25B / 8 lanes
    },
}


@dataclass
class RuntimeConfig:
    flowcell_type: str = "10B"
    n_lanes: int = FLOWCELL_PRESETS["10B"]["n_lanes"]
    lane_capacity_m: int = FLOWCELL_PRESETS["10B"]["lane_capacity_m"]

    output_dir: Optional[str] = None

    read1_len: int = DEFAULT_READ1
    read2_len: int = DEFAULT_READ2

    max_plans: int = 25  # keep your current behavior (MAX_SAVED_PLANS) by default


def config_path(base_dir: Path) -> Path:
    return base_dir / "config.json"


def default_config() -> RuntimeConfig:
    return RuntimeConfig()


def load_runtime_config(base_dir: Path) -> RuntimeConfig:
    p = config_path(base_dir)
    if not p.exists():
        return default_config()

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # tolerate partial config
        cfg = default_config()
        for k, v in (data or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
    except Exception:
        # if config is corrupted, fall back to default
        return default_config()


def save_runtime_config(base_dir: Path, cfg: RuntimeConfig) -> Path:
    p = config_path(base_dir)
    p.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    return p
