# Autonomous Agentic Coding Bot

This repo contains a multi-agent pipeline (Orchestrator → Planner → Worker → Reviewer) with project-specific specs stored under `projects/<project>/project.yaml`. Runs, logs, and memory stay inside the project tree.

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
- `projects/memory/` – memory index
- `projects/<project>/project.yaml` – required project spec

## Notes
- The worker is sandboxed to `projects/<project>` via `WORKSPACE_ROOT`; generated files belong under `projects/<project>/output/` (create if missing).
- Use `python -m agents.<agent>` to test individual agents if needed.
