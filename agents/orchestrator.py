import argparse
import json
import os
import re
import datetime
from pathlib import Path

from agents.planner import plan as planner_plan
from agents.worker import run_worker
from agents.reviewer import review
from utils.logger import log
from utils.memory import update_project_memory
from utils.project import load_project_spec, summarize_project_spec


MAX_REPAIR_ATTEMPTS = 2


def has_blocking_issues(review_data: dict) -> bool:
    issues = review_data.get("issues", []) if isinstance(review_data, dict) else []
    for issue in issues:
        severity = str(issue.get("severity", "")).lower()
        if severity in {"medium", "high"}:
            return True
    return False


def build_execution_summary(execution_results: list) -> str:
    """Render execution history into a text blob for the Reviewer."""
    execution_text = ""
    for result in execution_results:
        attempt_label = result.get("attempt", "initial")
        execution_text += f"\n--- Attempt: {attempt_label} | Step {result.get('step_id')} ---\n"
        execution_text += f"Description: {result.get('description', '')}\n"
        for cmd in result.get("worker_history", []):
            execution_text += f"COMMAND: {cmd.get('command', '')}\n"
            execution_text += f"RETURN CODE: {cmd.get('returncode', '')}\n"
            execution_text += f"STDOUT:\n{cmd.get('stdout', '')}\n"
            execution_text += f"STDERR:\n{cmd.get('stderr', '')}\n"
    return execution_text


def build_fix_request(goal: str, project_dir: Path, review_data: dict) -> str:
    issues = review_data.get("issues", []) if isinstance(review_data, dict) else []
    suggestions = review_data.get("suggestions", []) if isinstance(review_data, dict) else []
    return (
        "Repair request for existing project.\n"
        f"Project directory: {project_dir}\n"
        f"Original goal: {goal}\n\n"
        f"Reviewer flagged issues (JSON): {json.dumps(issues, indent=2)}\n"
        f"Reviewer suggestions: {json.dumps(suggestions, indent=2)}\n"
        "Return a revised plan JSON that will fix the issues in-place."
    )


def execute_steps(steps: list, project_dir: Path, attempt_label: str) -> list:
    execution_results = []
    for step in steps:
        step_id = step.get("id")
        description = step.get("description", "")

        log(
            msg=f"Executing step {step_id} ({attempt_label}):\n{description}",
            prefix="ORCH EXECUTE STEP"
        )

        worker_history = run_worker(description, workdir=str(project_dir))

        execution_results.append({
            "attempt": attempt_label,
            "step_id": step_id,
            "description": description,
            "worker_history": worker_history
        })

        log(
            msg=f"Step {step_id} ({attempt_label}) completed. History length: {len(worker_history)}",
            prefix="ORCH STEP DONE"
        )

    return execution_results


def slugify(text: str) -> str:
    """
    Turn an arbitrary goal string into a filesystem-friendly slug.
    Example: "Create FastAPI setup" -> "create-fastapi-setup"
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "task"

def make_project_dir(project_name: str) -> Path:
    """Ensure a project directory exists under ./projects for the given name."""
    project_root = Path("projects")
    project_root.mkdir(exist_ok=True)

    path = project_root / project_name
    path.mkdir(parents=True, exist_ok=True)

    return path


def make_run_filename(goal: str, project_dir: Path) -> Path:
    """
    Build a path like: <project_dir>/runs/create-fastapi-setup-2025-11-19.json
    """
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    slug = slugify(goal)[:50]  # avoid insanely long filenames
    filename = f"{slug}-{date_str}.json"

    runs_dir = project_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    return runs_dir / filename


def build_how_to_test(goal: str, project_dir: Path) -> str:
    """
    Build a human-readable 'how to test' guide for this project.
    Uses the goal and what files exist in the project directory
    to give concrete steps.
    """
    lines = []
    lines.append("To test this project:")

    # Always start by cd'ing into the project directory
    lines.append(f"1. Open a terminal and change into this directory:")
    lines.append(f"   cd {project_dir}")

    readme = project_dir / "README.md"
    server_run = project_dir / "SERVER_RUN.md"
    start_script = project_dir / "start_server.sh"

    step_num = 2

    if readme.exists():
        lines.append(f"{step_num}. Read the README for project-specific setup and usage:")
        lines.append(f"   cat README.md")
        step_num += 1

    if server_run.exists():
        lines.append(f"{step_num}. Follow the steps described in SERVER_RUN.md to start and test the server:")
        lines.append(f"   cat SERVER_RUN.md")
        step_num += 1

    if start_script.exists():
        lines.append(f"{step_num}. Ensure the server script is executable and run it to start the service:")
        lines.append(f"   chmod +x start_server.sh")
        lines.append(f"   ./start_server.sh")
        step_num += 1

    lines.append(f"{step_num}. If the project starts a web service, check the README or SERVER_RUN.md for the URL.")
    lines.append("   Common defaults include http://127.0.0.1:8000 or http://localhost:8000.")
    step_num += 1

    lines.append(f"{step_num}. If there is a tests/ directory or documented test command (e.g. pytest), run it to validate behavior.")

    if not any([readme.exists(), server_run.exists(), start_script.exists()]):
        lines.append("")
        lines.append("Note: This project does not include README.md, SERVER_RUN.md, or start_server.sh.")
        lines.append("You may need to inspect the files manually (e.g. main.py, app.py, fastapi_app/) to see how to run and test it.")

    return "\n".join(lines)


def write_project_summary(
    project_dir: Path,
    goal: str,
    planner_json: dict,
    execution_results: list,
    review_data: dict,
    repair_attempts: int = 0,
    plans: dict | None = None,
    status: str | None = None,
    blocking_issues_remaining: bool | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    final_plan: dict | None = None,
) -> None:
    """
    Write a PROJECT_INFO.json file into the project directory containing:
      - goal
      - plan (initial planner JSON)
      - plans (initial + repair plans)
      - review (structured reviewer JSON)
      - how_to_test (detailed instructions)
      - repair_attempts (number of repair passes executed)
      - execution_results (history across attempts)
      - status / blocking_issues_remaining
      - started_at / completed_at timestamps
    """
    summary = {
        "goal": goal,
        "project_dir": str(project_dir),
        "plan": planner_json,
        "review": review_data,
        "plans": plans or {},
        "execution_results": execution_results,
        "repair_attempts": repair_attempts,
        "status": status,
        "blocking_issues_remaining": blocking_issues_remaining,
        "started_at": started_at,
        "completed_at": completed_at,
        "final_plan": final_plan,
        "how_to_test": build_how_to_test(goal, project_dir),
    }

    out_path = project_dir / "PROJECT_INFO.json"
    with out_path.open("w") as f:
        json.dump(summary, f, indent=2)

    log(msg=f"Project summary written to {out_path}", prefix="ORCH PROJECT SUMMARY")


def verify_project_spec_access(project_path: str | Path):
    data = load_project_spec(project_path)
    summary = summarize_project_spec(data)
    print(f"[ORCH] Project spec summary: {summary}")


def orchestrate(goal: str, project_name: str, project_spec_path: Path):
    """
    Orchestrator:
      - Takes CEO-level goal
      - Calls Planner to generate steps
      - Parses steps
      - Feeds each step into Worker sequentially
      - Logs everything
      - Returns a summary
    """

    started_at = datetime.datetime.utcnow().isoformat()
    log(f"ORCHESTRATOR START — CEO GOAL:\n{goal}", prefix="ORCH START")

    if not project_spec_path.exists():
        raise FileNotFoundError(
            f"project.yaml is required at {project_spec_path}. Provide a project name with -n and ensure the file exists."
        )

    project_dir = make_project_dir(project_name)
    os.environ["PROJECT_SPEC_PATH"] = str(project_spec_path)
    os.environ["LOG_DIR"] = str(project_spec_path.parent / "logs")
    # Constrain worker operations to the project directory
    os.environ["WORKSPACE_ROOT"] = str(project_dir.resolve())
    project_id = project_dir.name
    log(f"Project directory for this run: {project_dir}", prefix="ORCH PROJECT")

    # 1) Call Planner (initial plan)
    planner_output = planner_plan(goal)
    log(f"PLANNER OUTPUT RAW:\n{planner_output}", prefix="ORCH PLANNER RAW")

    try:
        planner_json = json.loads(planner_output)
    except Exception as e:
        log(f"FAILED TO PARSE PLANNER JSON: {e}\nContent:\n{planner_output}", prefix="ORCH ERROR")
        raise ValueError(f"Invalid planner JSON: {e}")

    steps = planner_json.get("steps", [])
    if not steps:
        raise ValueError("Planner returned no steps.")

    log(f"PARSED {len(steps)} STEPS FROM PLANNER", prefix="ORCH PARSED")

    combined_plans = {"initial_plan": planner_json, "repair_plans": []}

    # 2) Execute initial plan
    execution_results = execute_steps(steps, project_dir, attempt_label="initial")

    # 3) First review
    execution_text = build_execution_summary(execution_results)
    planner_payload_for_review = json.dumps(combined_plans)
    review_json = review(
        goal=goal,
        planner_json=planner_payload_for_review,
        execution_summary=execution_text,
    )
    log(msg=f"REVIEWER OUTPUT:\n{review_json}", prefix="ORCH REVIEW")
    review_data = json.loads(review_json)

    # 4) Repair loop
    repair_attempts = 0
    while has_blocking_issues(review_data) and repair_attempts < MAX_REPAIR_ATTEMPTS:
        repair_attempts += 1
        log(
            msg=f"Starting repair attempt {repair_attempts}",
            prefix="ORCH REPAIR START",
        )

        fix_request = build_fix_request(goal, project_dir, review_data)
        repair_plan_output = planner_plan(fix_request)
        log(
            msg=f"Repair planner output (attempt {repair_attempts}):\n{repair_plan_output}",
            prefix="ORCH REPAIR PLAN RAW",
        )

        try:
            repair_plan_json = json.loads(repair_plan_output)
        except Exception as e:
            log(
                msg=f"FAILED TO PARSE REPAIR PLAN JSON: {e}\nContent:\n{repair_plan_output}",
                prefix="ORCH ERROR",
            )
            raise ValueError(f"Invalid repair planner JSON: {e}")

        combined_plans["repair_plans"].append({"attempt": repair_attempts, "plan": repair_plan_json})

        repair_steps = repair_plan_json.get("steps", [])
        if not repair_steps:
            log(
                msg="Repair plan contained no steps; stopping further repair attempts.",
                prefix="ORCH REPAIR COMPLETE",
            )
            break

        execution_results.extend(
            execute_steps(repair_steps, project_dir, attempt_label=f"repair-{repair_attempts}")
        )

        execution_text = build_execution_summary(execution_results)
        review_json = review(
            goal=goal,
            planner_json=json.dumps(combined_plans),
            execution_summary=execution_text,
        )
        review_data = json.loads(review_json)

        log(
            msg=f"Repair attempt {repair_attempts} complete. Reviewer response:\n{review_json}",
            prefix="ORCH REPAIR COMPLETE",
        )

    if has_blocking_issues(review_data) and repair_attempts >= MAX_REPAIR_ATTEMPTS:
        log(
            msg="Max repair attempts reached; medium/high issues may remain.",
            prefix="ORCH REPAIR LIMIT",
        )

    remaining_issues = has_blocking_issues(review_data)
    status = "success" if not remaining_issues else "needs_review"
    final_plan = (
        combined_plans.get("repair_plans", [])[-1].get("plan")
        if combined_plans.get("repair_plans")
        else planner_json
    )
    completed_at = datetime.datetime.utcnow().isoformat()

    # 5) Write project summary (includes repairs)
    write_project_summary(
        project_dir=project_dir,
        goal=goal,
        planner_json=planner_json,
        execution_results=execution_results,
        review_data=review_data,
        repair_attempts=repair_attempts,
        plans=combined_plans,
        status=status,
        blocking_issues_remaining=remaining_issues,
        started_at=started_at,
        completed_at=completed_at,
        final_plan=final_plan,
    )

    summary = {
        "goal": goal,
        "project_id": project_id,
        "project_dir": str(project_dir),
        "steps_executed": len(execution_results),
        "repair_attempts": repair_attempts,
        "results": execution_results,
        "review": review_data,
        "plans": combined_plans,
        "plan": planner_json,
        "status": status,
        "blocking_issues_remaining": remaining_issues,
        "started_at": started_at,
        "completed_at": completed_at,
        "final_plan": final_plan,
    }
    log(
        msg=(
            f"ORCHESTRATION COMPLETE — {len(execution_results)} steps executed, "
            f"repairs attempted: {repair_attempts}. Remaining blocking issues: {remaining_issues}"
        ),
        prefix="ORCH COMPLETE",
    )

    return summary



def main():
    parser = argparse.ArgumentParser(description="Run the orchestrator with required project spec.")
    parser.add_argument("goal", nargs="?", help="CEO-level goal")
    parser.add_argument("-n", "--name", dest="project_name", help="Project name (required)")
    args = parser.parse_args()

    project_name = args.project_name or input("Enter project name: ").strip()
    if not project_name:
        raise ValueError("Project name is required (use -n or provide when prompted).")

    goal = args.goal or input("Enter CEO-level goal: ").strip()
    if not goal:
        raise ValueError("Goal is required.")

    project_spec_path = Path("projects") / project_name / "project.yaml"
    if not project_spec_path.exists():
        raise FileNotFoundError(
            f"project.yaml is required at {project_spec_path}. Create it before running the orchestrator."
        )

    result = orchestrate(goal, project_name=project_name, project_spec_path=project_spec_path)

    # Save result to a JSON file with a descriptive name inside the project directory
    output_path = make_run_filename(goal, project_dir=Path(result.get("project_dir", project_dir)))
    with output_path.open("w") as f:
        json.dump(result, f, indent=2)

    try:
        project_id = result.get("project_id") or Path(result["project_dir"]).name
        update_project_memory(
            project_id=project_id,
            goal=goal,
            project_dir=result.get("project_dir", ""),
            run_summary_path=str(output_path),
            review_data=result.get("review", {}),
        )
    except Exception as e:
        log(msg=f"Failed to update memory index: {e}", prefix="ORCH MEMORY ERROR")

    print("\n=== ORCHESTRATOR SUMMARY ===")
    print(json.dumps(result, indent=2))
    print("============================")
    print(f"\nRun saved to: {output_path}")



if __name__ == "__main__":
    main()
