from pathlib import Path
from typing import Any, Dict

import yaml

from utils.logger import log


def load_campaign(path: str | Path) -> Dict[str, Any]:
    """Load a campaign YAML file, returning an empty dict if missing/invalid."""
    p = Path(path)
    if not p.exists():
        log(msg=f"Campaign file not found: {p}", prefix="CAMPAIGN WARN")
        return {}

    try:
        with p.open() as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log(msg=f"Failed to read campaign file {p}: {e}", prefix="CAMPAIGN WARN")
        return {}


def summarize_campaign(data: Dict[str, Any]) -> str:
    name = data.get("name") or data.get("title") or "(no name)"
    goal = data.get("goal") or data.get("description") or "(no goal/description)"
    extras = {k: v for k, v in data.items() if k not in {"name", "title", "goal", "description"}}
    extra_keys = ", ".join(sorted(extras.keys())) if extras else "none"
    return f"campaign name/title: {name}; goal/description: {goal}; extra fields: {extra_keys}"


def print_campaign_summary(path: str | Path) -> None:
    data = load_campaign(path)
    summary = summarize_campaign(data)
    print(f"Loaded campaign from {path}: {summary}")


__all__ = ["load_campaign", "summarize_campaign", "print_campaign_summary"]
