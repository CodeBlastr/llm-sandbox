import json
import re
import datetime
from pathlib import Path

from agents.planner import plan as planner_plan
from agents.worker import run_worker
from agents.reviewer import review
from utils.logger import log

def slugify(text: str) -> str:
    """
    Turn an arbitrary goal string into a filesystem-friendly slug.
    Example: "Create FastAPI setup" -> "create-fastapi-setup"
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "task"

def make_project_dir(goal: str) -> Path:
    """
    Create a dedicated project directory for this run, under ./projects.

    Example:
      projects/create-fastapi-setup-20251119-153045/
    """
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    slug = slugify(goal)[:50] or "project"
    project_root = Path("projects")
    project_root.mkdir(exist_ok=True)

    path = project_root / f"{slug}-{timestamp}"
    path.mkdir(parents=True, exist_ok=True)

    return path


def make_run_filename(goal: str) -> Path:
    """
    Build a path like: runs/create-fastapi-setup-2025-11-19.json
    """
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    slug = slugify(goal)[:50]  # avoid insanely long filenames
    filename = f"{slug}-{date_str}.json"

    runs_dir = Path("runs")
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
) -> None:
    """
    Write a PROJECT_INFO.json file into the project directory containing:
      - goal
      - plan (planner JSON)
      - review (structured reviewer JSON)
      - how_to_test (detailed instructions)
    """
    summary = {
        "goal": goal,
        "project_dir": str(project_dir),
        "plan": planner_json,
        "review": review_data,
        "how_to_test": build_how_to_test(goal, project_dir),
    }

    out_path = project_dir / "PROJECT_INFO.json"
    with out_path.open("w") as f:
        json.dump(summary, f, indent=2)

    log(msg=f"Project summary written to {out_path}", prefix="ORCH PROJECT SUMMARY")


def orchestrate(goal: str):
    """
    Orchestrator:
      - Takes CEO-level goal
      - Calls Planner to generate steps
      - Parses steps
      - Feeds each step into Worker sequentially
      - Logs everything
      - Returns a summary
    """

    log(f"ORCHESTRATOR START — CEO GOAL:\n{goal}", prefix="ORCH START")

    project_dir = make_project_dir(goal)
    log(f"Project directory for this run: {project_dir}", prefix="ORCH PROJECT")

    # 1) Call Planner
    planner_output = planner_plan(goal)
    log(f"PLANNER OUTPUT RAW:\n{planner_output}", prefix="ORCH PLANNER RAW")

    # 2) Parse Planner JSON
    try:
        planner_json = json.loads(planner_output)
    except Exception as e:
        log(f"FAILED TO PARSE PLANNER JSON: {e}\nContent:\n{planner_output}", prefix="ORCH ERROR")
        raise ValueError(f"Invalid planner JSON: {e}")

    steps = planner_json.get("steps", [])
    if not steps:
        raise ValueError("Planner returned no steps.")

    log(f"PARSED {len(steps)} STEPS FROM PLANNER", prefix="ORCH PARSED")

    execution_results = []

    # 3) Execute each step via Worker
    for step in steps:
        step_id = step.get("id")
        description = step.get("description", "")

        log(
            msg=f"Executing step {step_id}:\n{description}",
            prefix="ORCH EXECUTE STEP"
        )

        worker_history = run_worker(description, workdir=str(project_dir))

        execution_results.append({
            "step_id": step_id,
            "description": description,
            "worker_history": worker_history
        })

        log(
            msg=f"Step {step_id} completed. History length: {len(worker_history)}",
            prefix="ORCH STEP DONE"
        )

    # Generate a text execution summary for Reviewer
        # Generate a text execution summary for Reviewer
    execution_text = ""
    for result in execution_results:
        execution_text += f"\n--- Step {result['step_id']} ---\n"
        execution_text += f"Description: {result['description']}\n"
        for cmd in result["worker_history"]:
            execution_text += f"COMMAND: {cmd['command']}\n"
            execution_text += f"RETURN CODE: {cmd['returncode']}\n"
            execution_text += f"STDOUT:\n{cmd['stdout']}\n"
            execution_text += f"STDERR:\n{cmd['stderr']}\n"

    # Call Reviewer agent
    review_json = review(
        goal=goal,
        planner_json=planner_output,
        execution_summary=execution_text,
    )

    log(msg=f"REVIEWER OUTPUT:\n{review_json}", prefix="ORCH REVIEW")

    review_data = json.loads(review_json)

    # 🔥 NEW: write PROJECT_INFO.json into the project directory
    write_project_summary(
        project_dir=project_dir,
        goal=goal,
        planner_json=planner_json,
        execution_results=execution_results,
        review_data=review_data,
    )

    summary = {
        "goal": goal,
        "steps_executed": len(steps),
        "results": execution_results,
        "review": review_data,
    }

    log(
        msg=f"ORCHESTRATION COMPLETE — {len(steps)} steps executed. Review included.",
        prefix="ORCH COMPLETE",
    )

    return summary



def main():
    goal = input("Enter CEO-level goal: ")
    result = orchestrate(goal)

    # Save result to a JSON file with a descriptive name
    output_path = make_run_filename(goal)
    with output_path.open("w") as f:
        json.dump(result, f, indent=2)

    print("\n=== ORCHESTRATOR SUMMARY ===")
    print(json.dumps(result, indent=2))
    print("============================")
    print(f"\nRun saved to: {output_path}")



if __name__ == "__main__":
    main()
