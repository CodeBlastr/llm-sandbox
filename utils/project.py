from pathlib import Path
from typing import Any, Dict

import yaml

from utils.logger import log


def load_project_spec(path: str | Path) -> Dict[str, Any]:
    """Load a project YAML file, returning an empty dict if missing/invalid."""
    p = Path(path)
    if not p.exists():
        log(msg=f"Project spec file not found: {p}", prefix="PROJECT WARN")
        return {}

    try:
        with p.open() as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log(msg=f"Failed to read project spec {p}: {e}", prefix="PROJECT WARN")
        return {}


def summarize_project_spec(data: Dict[str, Any]) -> str:
    name = data.get("name") or data.get("title") or "(no name)"
    goal = data.get("goal") or data.get("description") or "(no goal/description)"
    extras = {k: v for k, v in data.items() if k not in {"name", "title", "goal", "description"}}
    extra_keys = ", ".join(sorted(extras.keys())) if extras else "none"
    return f"project name/title: {name}; goal/description: {goal}; extra fields: {extra_keys}"


def print_project_summary(path: str | Path) -> None:
    data = load_project_spec(path)
    summary = summarize_project_spec(data)
    print(f"Loaded project spec from {path}: {summary}")


__all__ = ["load_project_spec", "summarize_project_spec", "print_project_summary"]
