import json
import os
import subprocess
import datetime as dt
import yaml
from pathlib import Path

from utils.github_client import GitHubClientError, create_repo_if_missing
from utils.logger import log
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


def _run_git(args: list[str], project_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=True, check=False)


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


def _create_initial_commit(project_dir: Path) -> None:
    """
    Stage core project files and ensure there is at least one commit.
    Logs errors if commit fails but does not raise.
    """
    gitignore_path = project_dir / ".gitignore"
    output_dir = project_dir / "output"
    gitkeep_path = output_dir / ".gitkeep" if output_dir.exists() else None

    add_targets = [str(project_dir / "project.yaml"), str(gitignore_path)]
    if gitkeep_path and gitkeep_path.exists():
        add_targets.append(str(gitkeep_path))

    _run_git(["add", *add_targets], project_dir)
    commit = _run_git(["commit", "-m", "Initialize RDM project workspace"], project_dir)
    if commit.returncode != 0:
        log(msg=f"Initial commit failed: {commit.stderr}", prefix="PROJECT INIT")


def ensure_project_git_repo(project_dir: Path) -> None:
    """
    If project_dir is not already a git repo, initialize one and create
    an initial commit containing project.yaml and basic scaffolding.
    Does NOT configure any remotes or push.
    """
    git_dir = project_dir / ".git"
    if not git_dir.exists():
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

    # Ensure ignore and placeholder files exist before committing
    _ensure_project_gitignore(project_dir)

    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)
    gitkeep_path = output_dir / ".gitkeep"
    gitkeep_path.touch(exist_ok=True)

    # If no commits yet, stage core files and create the initial commit.
    head_check = _run_git(["rev-parse", "HEAD"], project_dir)
    if head_check.returncode != 0:
        add_targets: list[str] = []
        if (project_dir / "project.yaml").exists():
            add_targets.append("project.yaml")
        if (project_dir / ".gitignore").exists():
            add_targets.append(".gitignore")
        if (project_dir / "output" / ".gitkeep").exists():
            add_targets.append("output/.gitkeep")

        if add_targets:
            add_result = _run_git(["add", *add_targets], project_dir)
            if add_result.returncode != 0:
                log(msg=f"Initial git add failed: {add_result.stderr}", prefix="PROJECT INIT")

            commit_result = _run_git(["commit", "-m", "Initialize RDM project workspace"], project_dir)
            if commit_result.returncode != 0:
                log(msg=f"Initial commit failed: {commit_result.stderr}", prefix="PROJECT INIT")
        else:
            log(msg="Initial commit skipped: no files found to add.", prefix="PROJECT INIT")


def _configure_remote_and_push(project_dir: Path, remote_url: str) -> bool:
    existing_remote = _run_git(["remote", "get-url", "origin"], project_dir)
    if existing_remote.returncode != 0:
        add = _run_git(["remote", "add", "origin", remote_url], project_dir)
        if add.returncode != 0:
            log(msg=f"Failed to add remote: {add.stderr}", prefix="PROJECT INIT")
            return False

    branch_proc = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], project_dir)
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "main"
    log(msg=f"Pushing branch '{branch}' to {remote_url}", prefix="PROJECT INIT")

    # Ensure there is at least one commit before pushing.
    head_check = _run_git(["rev-parse", "HEAD"], project_dir)
    if head_check.returncode != 0:
        log(msg="Cannot push: branch has no commits (unborn HEAD).", prefix="PROJECT INIT")
        return False

    push = _run_git(["push", "-u", "origin", branch], project_dir)
    if push.returncode != 0:
        log(msg=f"Failed to push to remote: {push.stderr}", prefix="PROJECT INIT")
        return False

    return True


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

    raw_auto_remote = os.getenv("RDM_AUTO_CREATE_REMOTE", "")
    auto_remote = raw_auto_remote.lower() in {"1", "true", "yes", "on"}
    log(msg=f"RDM_AUTO_CREATE_REMOTE={raw_auto_remote}; auto_remote={auto_remote}", prefix="PROJECT INIT")
    if not auto_remote:
        log(msg="Skipping remote creation (RDM_AUTO_CREATE_REMOTE not set)", prefix="PROJECT INIT")
        return {
            "project_dir": project_dir,
            "session_state": session_state,
            "session_id": session_state["session_id"],
        }

    try:
        repo_info = create_repo_if_missing(project_name)
        remote_url = repo_info.get("clone_url") or repo_info.get("ssh_url")
        if not remote_url:
            raise GitHubClientError("No remote URL returned from GitHub")

        pushed = _configure_remote_and_push(project_dir, remote_url)
        if pushed:
            session_state["repo"] = _merge_defaults(session_state.get("repo"), {"url": remote_url})
            state_path.write_text(json.dumps(session_state, indent=2))

            project_spec_path = project_dir / "project.yaml"
            try:
                with project_spec_path.open() as f:
                    spec = yaml.safe_load(f) or {}
            except Exception:
                spec = {}
            spec["repo"] = _merge_defaults(spec.get("repo"), {"url": remote_url, "default_branch": None, "ssh_remote_name": None})
            with project_spec_path.open("w") as f:
                yaml.safe_dump(spec, f, sort_keys=False)

            log(msg=f"Remote GitHub repo created and pushed: {remote_url}", prefix="PROJECT INIT")
        else:
            log(msg="Remote creation succeeded but push failed; continuing locally.", prefix="PROJECT INIT")
    except GitHubClientError as e:
        log(msg=f"Remote creation failed: {e}", prefix="PROJECT INIT")
    except Exception as e:
        log(msg=f"Unexpected error during remote creation: {e}", prefix="PROJECT INIT")

    return {
        "project_dir": project_dir,
        "session_state": session_state,
        "session_id": session_state["session_id"],
    }


__all__ = ["initialize_project", "make_project_dir", "ensure_project_spec", "load_project_state", "ensure_project_git_repo"]
