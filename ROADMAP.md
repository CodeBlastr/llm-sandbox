# RDM – Roadmap

This roadmap is ordered to maximize safety first, autonomy second, and growth third.

---

## Phase 1: Safe Autonomy (Current Focus)

### 1. Auto-Merge Safety Gates (Deterministic)
**Purpose:** Prevent catastrophic merges before adding more AI autonomy.

Planned rules:
- Path allowlist:
  - Auto-merge ONLY if all changes are within:
    - `projects/<id>/`
    - (optionally) `projects/<id>/output/`
    - plus known metadata files (e.g., PROJECT_INFO.json)
- Hard-stop paths:
  - `/agents`, `/utils`, root infra, auth/secrets → manual only
- Diff thresholds:
  - Max files changed
  - Max lines added/removed
- Hard-stop patterns:
  - secrets
  - destructive shell commands
  - env / credential manipulation

Outcome:
- `auto` mode is safe to leave running.
- `manual` mode remains available as override.

---

## Phase 2: PR Review Agent (AI Gate)

### 2. AI PR Reviewer (Diff-Only)
**Purpose:** Catch logic issues and risky behavior beyond static rules.

Design:
- Runs ONLY after deterministic gates pass.
- Consumes:
  - PR diff
  - file list
  - policy results
- Outputs structured JSON:
  - decision: approve | manual_required | block
  - risk level
  - notes + checklist

Behavior:
- Posts review as a PR comment.
- Auto-merge proceeds only if:
  - mode=auto
  - decision=approve

Optional:
- Pluggable reviewer backend (OpenAI, Claude, etc.)
- Controlled via env var: `RDM_PR_REVIEW=on|off`

---

## Phase 3: Test Writer + Regression Safety

### 3. Test Writer Agent (Per-PR)
**Purpose:** Ensure new steps don’t silently break prior functionality.

Strategy:
- Each PR may trigger a **Test Writer Agent** that:
  - Generates or updates tests relevant to the change
  - Writes tests adjacent to project output
- Tests are:
  - Minimal
  - Fast
  - Focused on contract/regression, not perfection

Policies:
- Small/simple PRs → tests optional
- Multi-step or stateful PRs → tests required
- Missing tests in auto mode → downgrade to manual approval

Follow-up:
- Maintain a growing regression suite per project.
- Allow future runs to execute prior tests before proceeding.

---

## Phase 4: Persistent Memory + Resume Semantics

### 4. Long-Term Project Memory
**Purpose:** Enable true stop/resume without context loss.

Artifacts per project:
- Compact session summary
- Step history index
- Prior PR links
- Test inventory
- Known constraints / invariants

Effect:
- New runs start with summaries, not full history.
- Token usage remains bounded.
- Behavior approaches “Codex-style” continuity.

---

## Phase 5: RDM Builds & Markets Itself

### 5. Marketing & Growth Pipeline (Do Not Forget)
**Purpose:** RDM is not just a tool—it’s a product.

Planned capabilities:
- RDM-generated marketing sites
- Case studies from real runs
- Landing pages, blog posts, docs
- Automated demos / sandboxes
- SEO + content generation workflows

Key principle:
> The same PR-per-step, test-backed, review-gated workflow used for clients
> must also be used to build and market RDM itself.

---

## Guiding Principles
- PRs are truth.
- Small steps, always reviewable.
- Deterministic safety before AI judgment.
- Autonomy is earned, not assumed.
- RDM should eventually be able to explain itself to humans.

