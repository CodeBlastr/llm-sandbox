# Autonomous Agentic Coding Bot

This repo contains a multi-agent pipeline (Orchestrator → Planner → Worker → Reviewer) with project-specific specs stored under `projects/<project>/project.yaml`. Runs, logs, and memory stay inside the project tree.

## What RDM is NOT

- An AI model 
- A finished product
- A way to be lazy

## Prerequisites
- Docker & Docker Compose
- `.env` with:
  - `OPENAI_API_KEY` (required)
  - `CLOUDFLARE_API_TOKEN` (if doing Cloudflare work)
  - `GIT_USER_NAME` and `GIT_USER_EMAIL` (optional; used to set per-project git author)

## Build and start the container
```bash
docker compose up -d --build
```

## Run a project
1) Kick off a run (the orchestrator will scaffold the project if missing, including `project.yaml`):
2) From inside the container (or via `docker exec`):
```bash
python -m agents.orchestrator -n <project_name> "<goal>"
```

Examples:
```bash
docker exec -it llm-sandbox bash
python -m agents.orchestrator -n franchisetalk "Publish hello world to franchisetalk.com"
```

## Project output
- `projects/<project>/output/` – generated deliverables (apps, sites, assets, campaigns)
- `projects/<project>/runs/` – run summaries
- `projects/<project>/logs/` – agent logs
- `projects/<project>/state.json` – runtime session state (auto-created)
- `memory/` – memory index (across projects)
- `projects/<project>/project.yaml` – required project spec

## Project scaffolding, git, and state
- `python -m agents.orchestrator` uses `initialize_project` to create `projects/<name>/`, `output/`, `project.yaml`, and `state.json`.
- `project.yaml` is auto-generated if missing using the richer schema: `project_id`, `name`, `goal`, `description`, `repo{url,default_branch,ssh_remote_name}`, `default_execution_mode`, `rdm_agents{planner_id,worker_id,qa_id,analyst_id}`, `steps`, `metadata{created_at,tags}`.
- Each project gets its own git repo on first run:
  - Initialized on branch `main`, with local git config from `GIT_USER_NAME` / `GIT_USER_EMAIL` if set.
  - Project-level `.gitignore` ignores `state.json`, `logs/`, `runs/` (output is left trackable).
  - No remotes are added or pushed; you can add one later inside `projects/<name>`.

## Notes
- The worker is sandboxed to `projects/<project>` via `WORKSPACE_ROOT`; generated files belong under `projects/<project>/output/` (create if missing).
- Use `python -m agents.<agent>` to test individual agents if needed.
- To inspect a new project repo: `cd projects/<project> && git status` (initial commit contains `project.yaml`, `.gitignore`, and an `output/.gitkeep` placeholder).
