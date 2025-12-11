import datetime as dt
import json
import uuid
from pathlib import Path


def new_session_id(project_id: str) -> str:
    ts = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return f"{project_id}-{ts}-{uuid.uuid4().hex[:8]}"


def init_session_state(project_id: str, goal: str, project_root: Path, mode: str = "pipeline") -> dict:
    session_id = new_session_id(project_id)
    started_at = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    state = {
        "session_id": session_id,
        "project_id": project_id,
        "goal": goal,
        "status": "running",
        "started_at": started_at,
        "mode": mode,
    }

    state_path = project_root / "state.json"
    state_path.write_text(json.dumps(state, indent=2))
    return state


__all__ = ["new_session_id", "init_session_state"]
