# RDM – Reentry Context
NOTE TO SELF : I deleted all the test repos that were made from the working github connection. 


## What This Project Is
RDM (Rapid Deployment Machine) is an agentic system that:
- Creates a GitHub repo per project
- Executes work in discrete steps
- Commits each step to its own branch
- Opens **one PR minimum per step**
- Uses PRs as the authoritative execution log
- Supports auto-merge or manual approval via env config

The long-term goal is an autonomous-but-safe system that can:
- Build software projects
- Preserve state across restarts
- Be auditable via GitHub PR history
- Eventually build and market itself

---

## Current State (as of last session)

### ✅ Working
- GitHub repos are created automatically (private).
- One PR is created **per step**.
- PR titles and branches use **Run N / Step M** naming:
  - PR title: `<project> — Run <n> / Step <m> — <short goal>`
  - Branch: `rdm/run-<n>-step-<m>-<slug>`
- PR body includes:
  - session_id
  - run number
  - step number
  - commands executed
  - files changed
- `RDM_PR_APPROVAL_MODE=auto|manual` exists:
  - `manual` → open PR, stop, wait
  - `auto` → attempt merge, stop if blocked
- Merge-blocked behavior (conflicts, etc.) works correctly.
- `.env` loading is supported at orchestrator startup (project-level first, then repo root).

### ❌ Not Implemented Yet
- Auto-merge safety gates (path allowlist, diff limits, hard stops).
- AI-based PR review before auto-merge.
- Test generation per PR.
- Persistent test execution / regression protection.
- Marketing / growth pipeline for RDM itself.

---

## Key Design Decisions So Far
- **PRs are the primary audit log**, not conversation history.
- State must persist across restarts (run counters, summaries, PRs).
- Auto mode must be safe enough to run unattended.
- Agent roles should be small, composable, and policy-driven.
- Avoid sending full codebases to the LLM; use diff- and retrieval-first approaches.

---

## Open Questions to Resume With
- How strict should auto-merge gates be?
- Should AI PR review be required or optional?
- When should test-writing be mandatory vs best-effort?
- How do we prevent token usage from exploding as projects grow?

