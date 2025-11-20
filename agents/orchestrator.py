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
    execution_text = ""
    for result in execution_results:
        execution_text += f"\n--- Step {result['step_id']} ---\n"
        execution_text += f"Description: {result['description']}\n"
        for cmd in result['worker_history']:
            execution_text += f"COMMAND: {cmd['command']}\n"
            execution_text += f"RETURN CODE: {cmd['returncode']}\n"
            execution_text += f"STDOUT:\n{cmd['stdout']}\n"
            execution_text += f"STDERR:\n{cmd['stderr']}\n"

    # Call Reviewer agent
    review_json = review(
        goal=goal,
        planner_json=planner_output,
        execution_summary=execution_text
    )

    log(msg=f"REVIEWER OUTPUT:\n{review_json}", prefix="ORCH REVIEW")

    summary = {
        "goal": goal,
        "steps_executed": len(steps),
        "results": execution_results,
        "review": json.loads(review_json)
    }

    log(
        msg=f"ORCHESTRATION COMPLETE — {len(steps)} steps executed. Review included.",
        prefix="ORCH COMPLETE"
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
