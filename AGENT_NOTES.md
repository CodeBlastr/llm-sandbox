
# AGENT_NOTES.md  
_A concise technical reference for the entire local multi-agent system_

## 1. Project Purpose

This repository implements a **local multi-agent AI engineering system** that can:

- Plan software work (Planner agent)
- Execute work inside a sandbox directory (Worker agent)
- Review completed work (Reviewer agent)
- Orchestrate all agents (Orchestrator)
- Persist every run and project into structured artifacts
- Request secrets from the human in a safe way
- Execute bash commands safely inside defined project directories

It functions like a simplified, local-first version of Devin-style agents.

## 2. Directory Structure

```
/workspace
├── agents/
│   ├── planner.py
│   ├── worker.py
│   ├── reviewer.py
│   └── orchestrator.py
├── utils/
│   └── logger.py
├── projects/
│   └── <project-slug>-<timestamp>/
│        ├── generated project files (README.md, app/, scripts, etc.)
│        └── PROJECT_INFO.json
├── runs/
│   └── <slug>-YYYY-MM-DD.json
├── logs/
│   └── agent-YYYYMMDD.log
├── run.py
├── requirements.txt
├── compose.yml
└── Dockerfile
```

## 3. The Agents

### 3.1. Planner Agent (agents/planner.py)

Role:  
Acts as the **CTO**. Generates high-level multi-step plans as JSON.

System Behavior:
- Takes a natural language goal.
- Produces JSON only, of the form:

```
{
  "goal": "<restated goal>",
  "steps": [
    { "id": 1, "description": "..." },
    { "id": 2, "description": "..." }
  ]
}
```

Logging:
- Logs all requests and responses via `utils.logger.log()` with `PLANNER_*` prefixes.

### 3.2. Worker Agent (agents/worker.py)

Role:  
Acts as a **software engineer** that can execute bash commands.

System Behavior:
- Accepts a natural-language step description.
- Sends goal + shell history to OpenAI using a fixed system prompt.
- OpenAI must return **JSON only**:

```
{
  "command": "<bash command or empty string>",
  "done": true|false,
  "thoughts": "<natural language reasoning>"
}
```

Optional:  
Worker may return:

```
"ask_human": {
  "question": "...",
  "key_name": "ENV_VAR_NAME",
  "storage": "env"
}
```

Secret Handling:
- Worker prompts human using `getpass`.
- Secret is stored in:
  - `.env` file
  - `os.environ`
- Worker confirms the secret exists and appends a synthetic history event:
  - COMMAND: CONFIRM_SECRET <KEY>
  - RETURN CODE: 0

Execution:
- All bash commands executed via `run_shell(...)`.
- Worker supports `workdir` so commands run **inside project directories**, not inside the framework root.

Logging:
- Logs all LLM requests, responses, parsed JSON, and human secret events.

### 3.3. Reviewer Agent (agents/reviewer.py)

Role:  
Acts as **QA / code reviewer**. Evaluates Planner+Worker outcomes.

Input:
```
{
  "goal": "...",
  "planner_json": "...",
  "execution_summary": "human-readable summary"
}
```

Output JSON:
```
{
  "overall_assessment": "...",
  "issues": [
    { "type": "...", "description": "...", "severity": "low|medium|high" }
  ],
  "suggestions": [ "..." ]
}
```

Logging:
- Logs request payload, raw response, parsed content with `REVIEWER_*` prefixes.

### 3.4. Orchestrator Agent (agents/orchestrator.py)

Role:  
Acts as **CEO + Coordinator** of Planner → Worker → Reviewer.

Responsibilities:
1. Creates a dedicated project directory:
   ```
   projects/<slug>-<timestamp>/
   ```
2. Calls Planner to generate steps.
3. Iterates each step:
   - Calls `run_worker(step_description, workdir=project_dir)`
   - Collects full command history
4. Builds a textual execution summary.
5. Calls Reviewer to evaluate results.
6. Writes `PROJECT_INFO.json` (see below).
7. Writes run summary to:
   ```
   runs/<slug>-YYYY-MM-DD.json
   ```
8. Console prints final orchestrated summary.

Logging:
- Uses `ORCH_*` prefixes for all orchestration events.

## 4. Project Artifacts

### 4.1. Project Directory (projects/<slug>-timestamp/)
Contains all generated code and support files built by Worker.

Typical contents:
```
README.md
SERVER_RUN.md
start_server.sh
fastapi_app/
.v env/
PROJECT_INFO.json
```

### 4.2. PROJECT_INFO.json Structure

```
{
  "goal": "<original CEO goal>",
  "project_dir": "<absolute or relative path>",
  "plan": { ... parsed planner JSON ... },
  "review": { ... parsed reviewer JSON ... },
  "how_to_test": "multi-line test instructions"
}
```

### 4.3. how_to_test Section

Generated dynamically based on:
- Which files exist (README, SERVER_RUN.md, start script)
- The project directory path
- Reasonable startup/test procedure

## 5. Run Artifacts (runs/*.json)

Each orchestrator invocation writes a full run summary:

Filename pattern:
```
<slug>-YYYY-MM-DD.json
```

Contents:
```
{
  "goal": "...",
  "steps_executed": N,
  "results": [
     {
       "step_id": X,
       "description": "...",
       "worker_history": [
         { "command": "...", "stdout": "...", "stderr": "...", "returncode": 0 }
       ]
     }
  ],
  "review": { ... }
}
```

## 6. Logging System (utils/logger.py)

Everything the agents send/receive from OpenAI is logged here.

Directory:
```
logs/
  agent-YYYYMMDD.log
```

Each line:
```
[timestamp] [PREFIX] message...
```

Prefixes used:
- PLANNER REQUEST / RAW RESPONSE / PARSED
- WORKER REQUEST / RAW RESPONSE / PARSED
- REVIEWER REQUEST / RAW RESPONSE / PARSED
- ORCH START / ORCH EXECUTE STEP / ORCH REVIEW / ORCH COMPLETE
- SECRET CONFIRMED / SECRET CONFIRMATION FAILED

## 7. Running Individual Agents

Run Worker manually:
```
python run.py
```

Run Planner manually:
```
python -m agents.planner
```

Run Reviewer manually:
```
python -m agents.reviewer
```

Run full orchestrator:
```
python -m agents.orchestrator
```

## 8. Security Notes

- Worker knows how to request secrets without exposing values to logs or model.
- All work is executed inside per-project subdirectories to avoid contaminating agent codebase.
- Commands are executed inside `cwd=project_dir`.
- OpenAI never sees:
  - `.env`
  - actual secret values
  - stdout/stderr that contain secrets (we block that)

## 9. Future Extensions

1. Self-repair loop  
2. Docker Ops agent  
3. Tool abstraction  
4. Server-side agent definitions (OpenAI Agents Platform)

## 10. Summary

This repo implements a complete, extensible local multi-agent engineering pipeline with:
- Planner → Worker → Reviewer agents
- Safe secret handling
- Structured logging
- Per-project sandboxing
- Persistent run and project artifacts
- Rich project summaries including 'how to test'


## Cloudflare deployment status (franchisetalk.com)

- A Cloudflare API token is present in the environment, but Cloudflare returns:
  - `success: false`
  - error code `6003` / `6111`: "Invalid format for Authorization header" when calling `GET /client/v4/zones?name=franchisetalk.com`.
- This means the value stored in `CLOUDFLARE_API_TOKEN` is not a valid Cloudflare API token (e.g., it might be an API key, a malformed token, or otherwise not acceptable to Cloudflare).
- Without a valid token, I cannot:
  - Discover the zone ID for `franchisetalk.com`.
  - Create DNS records.
  - Deploy a Worker or Pages site.
- As a result, I cannot publish or verify a live `hello world` HTML site at `https://franchisetalk.com` via the Cloudflare API.

To proceed, provide a **Cloudflare API Token** (not the global API key) with at least:
- Zone:Read for `franchisetalk.com` (to list zones and get the zone ID)
- DNS:Edit (to manage DNS records if needed)
- Workers Scripts:Edit and Workers Routes:Edit **or** Pages:Edit (depending on whether you want a Worker-based or Pages-based deployment).

Once a valid token is available under `CLOUDFLARE_API_TOKEN`, I can:
1. Fetch the zone ID for `franchisetalk.com`.
2. Deploy a simple Worker or Pages project that serves the existing `projects/franchisetalk.com/index.html`.
3. Point the root of `franchisetalk.com` to that Worker/Pages deployment.
4. Verify via `curl https://franchisetalk.com` that the hello world HTML is live.

