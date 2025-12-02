# PROMPT.md
This file contains a single prompt you can paste into your VS Code Codex / OpenAI extension to implement Steps 1 and 2 of the system (Self-Repair Loop and Memory Layer). It is plain text with no rendered bullets so that you can copy/paste cleanly.

-------------------------------------------
BEGIN PROMPT TO PASTE INTO VS CODE
-------------------------------------------

I have a local multi-agent AI engineering framework already implemented in this repo. There is an AGENT_NOTES.md and a ROADMAP.md in the project root that describe the architecture. I want you to read AGENT_NOTES.md first to understand the current system, then implement the following two features directly in this codebase:

1) Self-repair loop (Reviewer → Planner → Worker → Reviewer)
2) Memory layer (persistent knowledge across runs)

Below are the requirements in detail. Please follow them precisely and update the code in place.

GENERAL CONTEXT
The system consists of Planner (agents/planner.py), Worker (agents/worker.py), Reviewer (agents/reviewer.py), Orchestrator (agents/orchestrator.py), and Logger (utils/logger.py). The Orchestrator does the following: creates a project directory in projects/<slug>-<timestamp>/, calls Planner to get steps, runs each step with run_worker(), generates an execution summary, calls Reviewer, writes PROJECT_INFO.json inside the project directory, and writes a run file under runs/. All OpenAI requests/responses are logged already.

-------------------------------------------
STEP 1: SELF-REPAIR LOOP
-------------------------------------------

Goal: After the initial Planner → Worker → Reviewer pass, if the Reviewer reports issues (especially with severity "medium" or "high"), the system should automatically attempt to repair the project in one or more additional passes.

High-level design:
• In Orchestrator, after the first review, examine the Reviewer JSON for issues.
• If any issues have severity medium or high, generate a “fix request” to the Planner. The fix request should include: the original goal, the reviewer’s issues, reviewer suggestions, and the project directory path.
• Call Planner again to create a repair plan, same JSON format as the initial plan.
• Execute the repair steps with Worker inside the same project directory.
• Build a combined execution summary including both original and repair histories.
• Call Reviewer again with the new summary.
• Repeat until no medium/high issues remain OR a limit (MAX_REPAIR_ATTEMPTS) is reached.

Implementation details:
• Modify agents/orchestrator.py to include a loop for repair attempts.
• Add a constant MAX_REPAIR_ATTEMPTS at the top of orchestrator.py.
• Maintain a combined execution_results array that includes results from both initial and repair passes.
• Update PROJECT_INFO.json after repairs, ensuring new fields (such as repair_attempts) are included.
• Update the final run summary file under runs/ to include both initial and repair results.
• Ensure that ORCH REPAIR START and ORCH REPAIR COMPLETE events are clearly logged.

-------------------------------------------
STEP 2: MEMORY LAYER
-------------------------------------------

Goal: Add a basic persistent memory system so agents can learn from prior runs and reuse knowledge.

High-level design:
• Create a new directory memory/ in the project root.
• Add a memory/project_index.json file that tracks:
  - Project ID (slug-timestamp)
  - Original goal
  - Project directory path
  - Run summary path
  - High-level review results (overall_assessment, issues summary, whether medium/high issues existed)
  - Created and updated timestamps

• After each full orchestrator run (including repairs), update memory/project_index.json:
  - If project exists, update it
  - Otherwise add a new entry

Use memory in Planner and Reviewer:
• In agents/planner.py, before calling OpenAI, load memory/project_index.json if it exists.
• Build a short “memory context” summarizing recent or similar past projects (simple heuristic is fine).
• Inject this memory context into the Planner’s user prompt.
• In agents/reviewer.py, do the same: load memory, summarize past issues, and include that context in the review prompt.
• Keep the added memory content small and bounded.

-------------------------------------------
GENERAL REQUIREMENTS
-------------------------------------------

• Do not break existing behavior.
• Use the existing logger system for all new logs.
• Extend PROJECT_INFO.json to include repair_attempts and other fields as needed.
• Ensure code style matches the rest of the project.
• Comment any complex logic.

Deliverables:
• Modify repository files directly to implement these features.
• After completing the changes, summarize:
  - Which files were modified
  - New functions added
  - How to run a normal orchestrated build with self-repair enabled
  - Where the memory is stored
  - How Planner and Reviewer are now reading that memory

