import json
from pathlib import Path


def load_and_increment_run_number(project_dir: Path) -> int:
    state_dir = project_dir / ".rdm"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"

    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}

    if not isinstance(state, dict):
        state = {}

    raw_value = state.get("run_number", 0)
    try:
        previous = int(raw_value)
    except (TypeError, ValueError):
        previous = 0

    run_number = max(previous, 0) + 1
    state["run_number"] = run_number
    state_path.write_text(json.dumps(state, indent=2))
    return run_number


__all__ = ["load_and_increment_run_number"]
