# RDM — Roadmap

This roadmap prioritizes **safety → autonomy → scalability → growth**.

---

## Phase 0 (Completed): Core PR-Driven Execution
✅ Repo auto-creation  
✅ One PR per step  
✅ PRs as audit log  
✅ Stop/resume via GitHub state  
✅ Auto vs manual approval modes  

---

## Phase 1 (Mostly Complete): Deterministic Safety Gates
**Goal:** Safe unattended execution

### Completed
- Path allowlist (repo-root relative)
- Hard-stop paths
- Diff thresholds
- Hard-stop pattern scanning
- Structured gate report
- Auto-merge only when gates pass

### Remaining (minor)
- Policy tuning (manual vs block distinctions)
- CI enforcement via tests (see Phase 1.5)

---

## Phase 1.5 (Next Focus): Test Foundation 🧪
**Goal:** Make the system refactorable without fear

### Tasks
- Introduce pytest test framework
- Unit tests for:
  - `utils/merge_gate.py`
  - `utils/github_publisher.py`
- Guardrail tests:
  - allowlist cannot be bypassed
  - auto-merge never fires when gate fails
  - manual mode never attempts merge
- Optional: minimal CI workflow

**Outcome**
- Deterministic behavior is locked
- Future changes are safe
- PR review ambiguity is eliminated

---

## Phase 2: AI PR Review Agent
**Goal:** Catch logic & safety issues beyond static rules

### Design
- Runs **only after deterministic gates pass**
- Consumes:
  - PR diff
  - file list
  - gate report
- Outputs structured decision:
  - approve | manual_required | block
- Posts review as PR comment
- Auto-merge proceeds only if:
  - approval_mode=auto
  - AI decision=approve

### Controls
- `RDM_PR_REVIEW=on|off`
- Pluggable LLM backend

---

## Phase 3: Test Writer + Regression Safety
**Goal:** Prevent silent breakage across runs

### Features
- Test Writer Agent per PR
- Tests are:
  - minimal
  - fast
  - contract-focused
- Policy driven:
  - small PR → tests optional
  - stateful/multi-step → tests required
- Auto mode downgrades to manual if required tests are missing
- Prior tests run before advancing steps

---

## Phase 4: Persistent Memory & Resume Semantics
**Goal:** True long-term continuity with bounded tokens

### Artifacts per project
- Compact session summary
- Step history index
- PR link index
- Test inventory
- Known constraints / invariants

### Outcome
- New runs load summaries, not full history
- Token usage stays bounded
- Behavior approaches Codex-style continuity

---

## Phase 5: RDM Builds & Markets Itself
**Goal:** RDM as a product, not just a tool

### Capabilities
- RDM-generated marketing site
- Case studies from real runs
- Docs, blogs, landing pages
- Demo sandboxes
- SEO + content workflows

### Principle
> The same PR-per-step, test-backed, review-gated workflow used for clients  
> must also be used to build and market RDM itself.

---

## Guiding Principles (Do Not Regress)
- PRs are truth
- Tests are contracts
- Deterministic gates before AI judgment
- Small steps, always reviewable
- Autonomy is earned
- RDM must be able to explain itself
