REPO_STRUCTURE_CONTRACT = """
REPO STRUCTURE CONTRACT (RDM Engine vs Project Workspace)

- The RDM Engine code lives in:
  - /agents
  - /utils
  - run.py
  - compose.yml, Dockerfile, and other root-level infra files.

- Project workspaces live under:
  - /projects/<project_id>/

Rules:
- Treat /projects/<project_id>/ as the ONLY place to create, modify, or delete files
  when working on a project.
- Do NOT modify RDM Engine code (agents, utils, orchestrator, run.py, etc.)
  unless the goal explicitly says you are refactoring the engine itself.
- If you are unsure where a file should go, default to /projects/<project_id>/.
- The orchestrator sets WORKSPACE_ROOT to the current project directory.
  You must stay within this workspace for all shell commands and file operations.
""".strip()
