import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from utils.logger import log


# Store memory under projects/ so project artifacts stay grouped
MEMORY_DIR = Path("projects") / "memory"
MEMORY_INDEX_PATH = MEMORY_DIR / "project_index.json"


def _ensure_memory_dir() -> None:
    MEMORY_DIR.mkdir(exist_ok=True)


def load_project_index() -> List[Dict[str, Any]]:
    """Load the project memory index, returning an empty list if missing/invalid."""
    _ensure_memory_dir()

    if not MEMORY_INDEX_PATH.exists():
        return []

    try:
        with MEMORY_INDEX_PATH.open() as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        log(msg=f"Failed to read memory index: {e}", prefix="MEMORY WARN")

    return []


def save_project_index(entries: List[Dict[str, Any]]) -> None:
    """Persist the project memory index to disk."""
    _ensure_memory_dir()
    with MEMORY_INDEX_PATH.open("w") as f:
        json.dump(entries, f, indent=2)


def _truncate(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _has_medium_or_high(issues: List[Dict[str, Any]]) -> bool:
    for issue in issues or []:
        sev = str(issue.get("severity", "")).lower()
        if sev in {"medium", "high"}:
            return True
    return False


def _build_review_summary(review_data: Dict[str, Any]) -> Dict[str, Any]:
    issues = review_data.get("issues", []) if isinstance(review_data, dict) else []
    suggestions = review_data.get("suggestions", []) if isinstance(review_data, dict) else []

    return {
        "overall_assessment": review_data.get("overall_assessment", ""),
        "issues": issues,
        "suggestions": suggestions,
        "has_medium_or_high": _has_medium_or_high(issues),
    }


def update_project_memory(
    *,
    project_id: str,
    goal: str,
    project_dir: str,
    run_summary_path: str,
    review_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Upsert a project entry into the memory index."""

    index = load_project_index()
    now = datetime.utcnow().isoformat()
    review_summary = _build_review_summary(review_data or {})

    existing = next((e for e in index if e.get("project_id") == project_id), None)

    if existing:
        existing.update(
            {
                "goal": goal,
                "project_dir": project_dir,
                "run_summary_path": run_summary_path,
                "review": review_summary,
                "updated_at": now,
            }
        )
        entry = existing
    else:
        entry = {
            "project_id": project_id,
            "goal": goal,
            "project_dir": project_dir,
            "run_summary_path": run_summary_path,
            "review": review_summary,
            "created_at": now,
            "updated_at": now,
        }
        index.append(entry)

    save_project_index(index)
    log(msg=f"Memory index updated for project {project_id}", prefix="MEMORY UPDATE")
    return entry


def summarize_recent_projects(goal: str | None = None, max_entries: int = 3) -> str:
    """
    Build a compact text summary of recent projects and their review outcomes.

    Heuristic: we surface the most recently updated entries (bounded by
    ``max_entries``). This keeps prompt injections small while still giving
    historical signal.
    """
    if not MEMORY_INDEX_PATH.exists():
        return ""

    index = load_project_index()
    if not index:
        return ""

    target_words = set(re.findall(r"[a-z0-9]+", goal.lower())) if goal else set()

    def entry_score(entry: Dict[str, Any]) -> tuple:
        words = set(re.findall(r"[a-z0-9]+", str(entry.get("goal", "")).lower()))
        overlap = len(words & target_words) if target_words else 0
        return (overlap, entry.get("updated_at", ""))

    sorted_entries = sorted(index, key=entry_score, reverse=True)[:max_entries]

    lines = ["Recent/related project memory:"]
    for entry in sorted_entries:
        review = entry.get("review", {})
        assessment = _truncate(str(review.get("overall_assessment", "")), 140)
        has_medium_high = bool(review.get("has_medium_or_high"))
        issues = review.get("issues") or []
        first_issue = _truncate(str(issues[0].get("description", "")), 120) if issues else ""

        lines.append(
            f"- {entry.get('project_id', 'unknown')}: goal='{_truncate(entry.get('goal', ''), 80)}'; "
            f"assessment='{assessment}'; medium/high issues={has_medium_high}; first_issue='{first_issue}'"
        )

    return "\n".join([line for line in lines if line.strip()])


__all__ = [
    "load_project_index",
    "save_project_index",
    "summarize_recent_projects",
    "update_project_memory",
]
