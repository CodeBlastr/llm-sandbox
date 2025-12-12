import json
import os
import subprocess
import datetime as dt
import yaml
from pathlib import Path

from utils.session import init_session_state


def make_project_dir(project_name: str) -> Path:
    """Ensure a project directory exists under ./projects for the given name."""
    project_root = Path("projects")
    project_root.mkdir(exist_ok=True)

    path = project_root / project_name
    path.mkdir(parents=True, exist_ok=True)
    (path / "output").mkdir(exist_ok=True)

    return path


def ensure_project_spec(project_name: str, project_spec_path: Path, goal: str, mode: str) -> None:
    """
    Ensure project.yaml exists and matches the richer schema.
    - Prompts for display name/description when creating new files.
    - Enriches existing files non-destructively (adds missing keys only).
    """
    project_spec_path.parent.mkdir(parents=True, exist_ok=True)

    desired_mode = "simple" if mode == "simple" else "pipeline"  # normalize mode for project spec
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _base_spec(name_value: str, description_value: str) -> dict:
        return {
            "project_id": project_name,
            "name": name_value,
            "goal": goal,
            "description": description_value,
            "repo": {"url": None, "default_branch": None, "ssh_remote_name": None},
            "default_execution_mode": desired_mode,
            "rdm_agents": {"planner_id": None, "worker_id": None, "qa_id": None, "analyst_id": None},
            "steps": [],
            "metadata": {"created_at": now, "tags": []},
        }

    if project_spec_path.exists():
        try:
            with project_spec_path.open() as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

        spec = _base_spec(
            existing.get("name") or project_name,
            existing.get("description") or "",
        )
        spec.update({k: v for k, v in existing.items() if k in {"project_id", "name", "goal", "description"}})

        spec["repo"] = _merge_defaults(existing.get("repo"), spec["repo"])
        spec["rdm_agents"] = _merge_defaults(existing.get("rdm_agents"), spec["rdm_agents"])
        spec["metadata"] = _merge_defaults(existing.get("metadata"), spec["metadata"])
        spec["default_execution_mode"] = existing.get("default_execution_mode", desired_mode)
        spec["steps"] = existing.get("steps", spec["steps"])

        with project_spec_path.open("w") as f:
            yaml.safe_dump(spec, f, sort_keys=False)
        return

    print(f"Project spec not found at {project_spec_path}.")
    name = input(f"Enter project display name [{project_name}]: ").strip() or project_name
    description = input("Enter project description: ").strip() or ""

    data = _base_spec(name, description)

    with project_spec_path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    print(f"Created project spec at {project_spec_path}")


def load_project_state(project_dir: Path) -> dict:
    """Load and return projects/<name>/state.json, raising a clear error if missing."""
    state_path = project_dir / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found at {state_path}")
    with state_path.open() as f:
        return json.load(f)


def _merge_defaults(existing: dict | None, defaults: dict) -> dict:
    merged = {**defaults}
    if isinstance(existing, dict):
        merged.update(existing)
    return merged


def _enrich_session_state(state: dict) -> dict:
    state.setdefault("default_execution_mode", "pipeline")
    state.setdefault("steps", [])
    state.setdefault("current_step_index", None)
    state.setdefault("log", [])
    state["repo"] = _merge_defaults(
        state.get("repo"),
        {"url": None, "default_branch": None, "ssh_remote_name": None},
    )
    state["rdm_agents"] = _merge_defaults(
        state.get("rdm_agents"),
        {"planner_id": None, "worker_id": None, "qa_id": None, "analyst_id": None},
    )
    state.setdefault("completed_at", None)
    return state


def _ensure_project_gitignore(project_dir: Path) -> Path:
    gitignore_path = project_dir / ".gitignore"
    desired = ["state.json", "logs/", "runs/", ".DS_Store"]

    existing = []
    if gitignore_path.exists():
        existing = [line.rstrip("\n") for line in gitignore_path.read_text().splitlines()]

    combined = existing[:]
    for entry in desired:
        if entry not in combined:
            combined.append(entry)

    gitignore_path.write_text("\n".join([line for line in combined if line.strip() != ""]) + "\n")
    return gitignore_path


def ensure_project_git_repo(project_dir: Path) -> None:
    """
    If project_dir is not already a git repo, initialize one and create
    an initial commit containing project.yaml and basic scaffolding.
    Does NOT configure any remotes or push.
    """
    if (project_dir / ".git").exists():
        return

    # Prefer main as default branch; fall back silently if -b is unsupported.
    init_result = subprocess.run(["git", "init", "-b", "main"], cwd=project_dir, check=False)
    if init_result.returncode != 0:
        subprocess.run(["git", "init"], cwd=project_dir, check=False)
        subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=project_dir, check=False)

    git_user_email = os.getenv("GIT_USER_EMAIL")
    git_user_name = os.getenv("GIT_USER_NAME")
    if git_user_email:
        subprocess.run(["git", "config", "user.email", git_user_email], cwd=project_dir, check=False)
    if git_user_name:
        subprocess.run(["git", "config", "user.name", git_user_name], cwd=project_dir, check=False)

    gitignore_path = _ensure_project_gitignore(project_dir)

    output_dir = project_dir / "output"
    gitkeep_path = None
    if output_dir.exists():
        output_dir.mkdir(exist_ok=True)
        gitkeep_path = output_dir / ".gitkeep"
        gitkeep_path.touch(exist_ok=True)

    add_targets = [str(project_dir / "project.yaml"), str(gitignore_path)]
    if gitkeep_path:
        add_targets.append(str(gitkeep_path))

    subprocess.run(["git", "add"] + add_targets, cwd=project_dir, check=False)
    subprocess.run(["git", "commit", "-m", "Initialize RDM project workspace"], cwd=project_dir, check=False)


def initialize_project(goal: str, project_name: str, mode: str) -> dict:
    """
    Centralized project initialization:
      - create project directory and output/
      - ensure project.yaml exists
      - create/enrich state.json
    """
    project_dir = make_project_dir(project_name)
    project_spec_path = project_dir / "project.yaml"
    ensure_project_spec(project_name, project_spec_path, goal, mode)

    base_state = init_session_state(
        project_id=project_name,
        goal=goal,
        project_root=project_dir,
        mode=mode,
    )

    state_path = project_dir / "state.json"
    if not state_path.exists():
        state_path.write_text(json.dumps(base_state, indent=2))

    try:
        on_disk_state = load_project_state(project_dir)
    except Exception:
        on_disk_state = base_state

    enriched_state = _enrich_session_state(on_disk_state)
    state_path.write_text(json.dumps(enriched_state, indent=2))
    session_state = load_project_state(project_dir)

    ensure_project_git_repo(project_dir)

    return {
        "project_dir": project_dir,
        "session_state": session_state,
        "session_id": session_state["session_id"],
    }


__all__ = ["initialize_project", "make_project_dir", "ensure_project_spec", "load_project_state", "ensure_project_git_repo"]
