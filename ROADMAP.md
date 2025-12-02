# ROADMAP.md
_High-level roadmap for evolving the local multi-agent system_

This document describes the **forward-looking roadmap** for the AI engineering framework.

> Note: Earlier design discussions included:
> - Step 1: Self-repair loop (Reviewer → Planner → Worker → Reviewer)
> - Step 2: Memory layer (persistent knowledge across runs)
>
> Those two are **intentionally omitted** from this roadmap file, as they will be implemented interactively.

---

## 3. Replace Raw Bash With a Structured Tool Layer

Currently, the Worker agent outputs raw bash commands. This is powerful but brittle and risky.

### Goals

- Introduce a **tool API** that the Worker calls instead of raw shell.
- Make all file and process operations go through well-defined Python functions.
- Improve safety, auditability, and reliability.

### Key Tools (Initial Set)

- `read_file(path)`
- `write_file(path, content)`
- `append_file(path, content)`
- `list_dir(path)`
- `remove_file(path)`
- `copy_file(src, dst)`
- `run_process(command, args, cwd)`
- `git_status()`
- `git_diff()`
- `git_commit(message)`

### Changes Required

- Update Worker system prompt:
  - Instead of `"command": "<bash string>"`, allow something like `"tool_call": { ... }`.
- Implement a tool dispatcher in Python:
  - Parse the Worker JSON.
  - Dispatch to the correct tool implementation.
  - Capture success/failure and log everything.
- Add safety rules:
  - Restrict filesystem paths to project directories.
  - Disallow destructive operations outside the sandbox.

---

## 4. Add a DockerOps Agent for Multi-Container Workflows

The system will eventually need to interact with **sibling containers** for integration tests, services, and databases.

### Goals

- Provide a dedicated Docker operations agent (DockerOps).
- Allow Planner/Orchestrator to ask DockerOps to:
  - Inspect containers.
  - Execute commands in other containers.
  - Tail logs.
  - Restart services.

### Key Capabilities

- `docker_ps()` – list running containers.
- `docker_exec(container_name, command)`
- `docker_logs(container_name, tail=N)`
- `docker_restart(container_name)`

### Implementation Sketch

- Mount the Docker socket into the agent container:
  - `/var/run/docker.sock:/var/run/docker.sock`
- Implement DockerOps as:
  - A separate Python module and/or agent with its own system prompt.
  - A set of tools called by the Orchestrator or Planner.
- Extend Orchestrator to:
  - Ask DockerOps to stand up or validate services as part of a run.
  - Include DockerOps outputs in the execution summary and review.

---

## 5. Move Planner and Reviewer to Server-Side Agents (OpenAI Agents Platform)

Once local behavior is stable, Planner and Reviewer can be migrated to OpenAI’s Agent Platform.

### Goals

- Reduce per-call token overhead for system prompts.
- Centralize agent configuration (instructions, tools, safety).
- Use prompt caching and server-side optimizations.

### Migration Steps

- Extract current Planner and Reviewer prompts into standalone agent definitions.
- Register any necessary tools (if/when used) on the platform.
- Update local code to:
  - Call Planner and Reviewer via their agent IDs instead of raw `chat.completions`.
- Keep Worker and DockerOps local:
  - They run code, access the filesystem, and interact with Docker.

---

## 6. Unified CLI for CEO-Level Commands

The system is currently invoked via different entrypoints:

- `python -m agents.orchestrator`
- `python run.py`
- `python -m agents.planner`
- `python -m agents.reviewer`

### Goal

Create a single CLI script to drive the entire system in a consistent way.

### Example Commands

- `ai build "Create a FastAPI project with auth"`
- `ai fix runs/some-run.json`
- `ai test projects/some-project-dir`

### Implementation Sketch

- Add `ai.py` or `cli.py` at the project root.
- Use `argparse` or `typer` for a user-friendly CLI.
- Map subcommands to:
  - Orchestrator (build)
  - Self-repair (fix; implemented later)
  - Test/verification flows

---

## 7. Web Dashboard for Runs and Projects

A web UI will dramatically improve observability and usability.

### Goals

- Display runs, projects, reviews, and logs in a browser.
- Allow manual triggers (re-run, repair, test).
- Show agent reasoning and actions in a timeline view.

### Features

- Runs list:
  - Status (success/fail/needs repair)
  - Goal
  - Timestamp
- Project view:
  - Link to project directory.
  - Rendered PROJECT_INFO.json (goal, plan, review, how_to_test).
- Logs:
  - Filterable by agent (Planner/Worker/Reviewer/Orchestrator).
  - Search by keyword.

### Implementation Ideas

- Lightweight FastAPI app serving:
  - A simple frontend (React, Svelte, or plain HTML).
  - JSON APIs to read `runs/`, `projects/`, and `logs/`.
- Optional integration with editor (VS Code, etc.) via links.

---

## 8. Test Suite for Agents and Tools

Unit tests and integration tests are essential once the system stabilizes.

### Goals

- Ensure Planner, Worker, Reviewer, and Orchestrator behave as expected.
- Avoid regressions when prompts or code change.
- Safely validate tool layer behavior.

### Tests to Add

- Planner tests:
  - Given a goal, returns valid JSON with steps.
  - Steps are non-empty and ordered.
- Worker tests (with mocked OpenAI responses):
  - Executes simple tool calls or commands.
  - Handles `ask_human` logic safely.
- Reviewer tests:
  - Produces valid JSON with required keys.
  - Handles missing or partial inputs.
- Orchestrator tests:
  - Orchestrates a synthetic plan and stores artifacts correctly.
  - Writes PROJECT_INFO.json and run summaries.

---

## 9. Multi-Agent Parallelism and Specialization

As complexity grows, different agent specializations and parallel execution become valuable.

### Possible Specialized Agents

- Frontend worker (React, CSS, UI).
- Backend worker (APIs, databases).
- DevOps worker (CI/CD, deployments, observability).
- Security reviewer (vulnerabilities, secrets, hardening).
- Performance reviewer (latency, resource usage patterns).

### Parallel Execution

- Planner splits work into parallelizable chunks.
- Orchestrator spins multiple Worker instances in parallel.
- Reviewer aggregates and integrates results.

---

## 10. Production-Grade Migration and Hardening

Once the system is robust and useful, prepare it for real workloads.

### Steps

- Harden security:
  - Strict filesystem boundaries.
  - Strict command allowlists.
  - Strong isolation between agent framework and target projects.
- Observability:
  - Structured logging (JSON logs).
  - Metrics for runs, durations, failures, and repairs.
- Deployment options:
  - As a local dev tool (current behavior).
  - As a service accessible over an internal API.
  - Optionally as a cloud-hosted orchestrator with local workers.

---

## Summary

This roadmap focuses on:

- Tooling and safety (structured tools, DockerOps, test suite).
- Scalability (server-side Planner/Reviewer, multi-agent parallelism).
- UX (unified CLI, dashboard).
- Production readiness (security, observability, deployment).

Steps for self-repair loops and memory are being designed and implemented separately, but this roadmap provides the broader direction for turning the current system into a robust, production-ready AI engineering platform.
