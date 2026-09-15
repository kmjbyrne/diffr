import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".local" / "share" / "diffr" / "config.json"

DEFAULTS = {
    "scan_paths": [],
    "max_depth": 2,
    "ai_provider": "claude",
    "last_repo": None,
    "last_branch": None,
    "last_base": None,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            stored = json.load(f)
        merged = {**DEFAULTS, **stored}
        return merged
    return dict(DEFAULTS)


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
