import os
import subprocess
import json
from json import JSONDecodeError
import shlex
from getpass import getpass
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import log
from utils.project import load_project_spec, summarize_project_spec
from utils.contracts import REPO_STRUCTURE_CONTRACT

# Load .env values into the environment (including any secrets you already put there)
load_dotenv(override=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")
MAX_PROMPT_CHARS = int(os.getenv("WORKER_MAX_PROMPT_CHARS", "5000"))
HISTORY_CHAR_LIMIT = int(os.getenv("WORKER_HISTORY_CHAR_LIMIT", str(int(MAX_PROMPT_CHARS * 0.6))))


def run_shell(command: str, workdir: str | None = None) -> dict:
    """Execute a shell command and capture output with safety checks."""
    allowed_root = Path(os.getenv("WORKSPACE_ROOT", "/workspace")).resolve()
    cwd_path = Path(workdir or os.getcwd()).resolve()

    if allowed_root not in cwd_path.parents and cwd_path != allowed_root:
        return {
            "command": command,
            "stdout": "",
            "stderr": f"Unsafe workdir outside allowed root: {cwd_path}",
            "returncode": -1,
        }

    def is_safe(cmd: str) -> tuple[bool, str]:
        lowered = cmd.lower()
        banned_phrases = ["rm -rf /", "rm -rf --no-preserve-root", "sudo rm", "mkfs", ":(){:|:&};:"]
        for phrase in banned_phrases:
            if phrase in lowered:
                return False, f"Blocked dangerous command pattern: {phrase}"

        # Out-of-bounds guardrail: block commands that explicitly target engine files/dirs
        engine_markers = ["/agents", "./agents", " agents/", "/utils", "./utils", " utils/", "run.py", "dockerfile", "compose.yml"]
        for marker in engine_markers:
            if marker in cmd.lower():
                return False, f"Blocked out-of-bounds target (engine code): {marker}"

        # Only inspect the first line (shell command), ignore heredoc payload
        first_line = cmd.splitlines()[0].strip()
        try:
            tokens = shlex.split(first_line)
        except Exception:
            tokens = first_line.split()

        for tok in tokens:
            if tok.startswith("/") and len(tok) > 1:
                try:
                    p = Path(tok).resolve()
                    if allowed_root not in p.parents and p != allowed_root:
                        return False, f"Blocked absolute path outside workspace: {p}"
                except Exception:
                    return False, f"Blocked unresolvable absolute path: {tok}"
            if tok == "sudo":
                return False, "Blocked use of sudo"
        return True, ""

    safe, reason = is_safe(command)
    if not safe:
        log(msg=reason, prefix="WORKER SAFETY")
        return {
            "command": command,
            "stdout": "",
            "stderr": reason,
            "returncode": -1,
        }

    try:
        env = os.environ.copy()

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        return {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    except Exception as e:
        return {
            "command": command,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


def save_secret(key_name: str, value: str, storage: str = "env") -> None:
    """
    Store a secret locally WITHOUT ever sending it to the model.

    - Sets it in this process's environment so subprocesses (shell commands) can use it.
    - Optionally appends to .env so it persists across runs.
    """
    if storage == "env":
        # Set in current process environment
        os.environ[key_name] = value

        # Persist in .env (in the mounted workspace)
        env_path = ".env"
        line = f"\n{key_name}={value}\n"

        try:
            with open(env_path, "a") as f:
                f.write(line)
        except Exception as e:
            # Non-fatal; just log to stderr-equivalent
            print(f"[WARN] Failed to write secret {key_name} to .env: {e}")


def build_system_prompt() -> str:
    workspace_root = os.getenv("WORKSPACE_ROOT", "/workspace")
    default_output_dir = str(Path(workspace_root) / "output")
    output_dir = os.getenv("PROJECT_OUTPUT_DIR", default_output_dir)
    output_note = (
        f"\nProject output root for this run: {output_dir}\n"
        "Place all generated files inside this directory (create subfolders as needed). "
        "Do NOT create nested 'projects' directories or alternate roots."
    )
    return (
        f"{REPO_STRUCTURE_CONTRACT}\n"
        f"\nWorkspace root for this run: {workspace_root}"
        f"{output_note}\n\n"
        "You are an autonomous software engineer with access to a bash shell.\n"
        "You respond ONLY with valid JSON. The JSON MUST have these keys:\n"
        "  - command: string (the shell command to run, or \"\" if none)\n"
        "  - done: boolean (true if the overall goal is achieved)\n"
        "  - thoughts: string (your reasoning, for the human to read)\n"
        "You MAY also include an optional key:\n"
        "  - ask_human: object with keys {question: string, key_name: string, storage: string}\n"
        "  - needs_human: object with keys {reason: string} to pause automation when you believe human intervention is required.\n"
        "Truth vs fiction rule: treat an action as TRUE only when its result is verifiable (successful command, expected output or secondary source). If a result is not verifiable or fails, treat it as FICTION and simplify; propose the smallest testable next step.\n"
        "One-step rule: propose exactly one command per response, wait for its result, and do not move on until that step is confirmed (success exit + simple verification if needed). Prefer a short verification command after changes before proceeding. Only set done=true after a verified success.\n"
        "Safety rule: stay within the workspace (/workspace) and project directories; do NOT use absolute paths outside them; do NOT run destructive commands (e.g., rm -rf /, sudo).\n"
        "Non-interactive rule: commands must be non-interactive; add flags like --yes/-y or use env (NPM_CONFIG_YES, NPX_YES) to avoid prompts. If a command times out waiting for input, simplify and try a non-interactive alternative.\n"
        "DNS/propagation rule: avoid tight polling; if you need to recheck, include an explicit delay (e.g., sleep 60) before the next check.\n"
        "Use ask_human ONLY when you cannot proceed without a human-provided secret "
        "such as an API key.\n"
        "\n"
        "The controller will do the following when you use ask_human:\n"
        "  1) It will ask the human your 'question'.\n"
        "  2) It will store the secret under environment variable name 'key_name'.\n"
        "  3) It will verify that environment variable actually exists.\n"
        "  4) If verification succeeds, a step will appear in HISTORY like:\n"
        "       COMMAND: CONFIRM_SECRET <KEY_NAME>\n"
        "       STDOUT: Secret <KEY_NAME> is present in environment.\n"
        "  5) If verification fails, a step will appear like:\n"
        "       COMMAND: CONFIRM_SECRET_FAILED <KEY_NAME>\n"
        "       STDERR: Secret <KEY_NAME> is NOT present in environment.\n"
        "\n"
        "You MUST NOT print, log, or write the actual secret value anywhere.\n"
        "Do not echo it, do not store it in files, and do not include it in your JSON.\n"
        "\n"
        "When deciding what to do next, you may rely on CONFIRM_SECRET steps in HISTORY\n"
        "as evidence that the corresponding environment variable exists and is usable.\n"
    )


def call_llm(goal: str, history: list, session_id: str | None = None) -> dict:
    """Send goal + history to the LLM and get the next action."""
    system_prompt = build_system_prompt()

    def format_history(entries, limit_chars: int | None = None) -> str:
        text = ""
        for step in entries:
            text += (
                f"COMMAND: {step['command']}\n"
                f"RETURN CODE: {step['returncode']}\n"
                f"STDOUT:\n{step['stdout']}\n"
                f"STDERR:\n{step['stderr']}\n\n"
            )
        if limit_chars and len(text) > limit_chars:
            text = text[-limit_chars:]
        return text

    history_text = format_history(history, HISTORY_CHAR_LIMIT)

    session_line = f"SESSION_ID: {session_id}\n" if session_id else ""

    user_prompt = (
        f"{session_line}GOAL:\n{goal}\n\n"
        f"HISTORY:\n{history_text}\n"
        "Decide what to do next. Either:\n"
        "  - Provide the next shell command in 'command', or\n"
        "  - If you cannot proceed without human-provided secrets, use 'ask_human'.\n"
        "  - If you believe progress is blocked and requires a human decision (e.g., missing permissions, external approval), set 'needs_human' with a reason and leave command empty.\n"
        "The controller will verify that requested secrets exist as environment\n"
        "variables before proceeding."
    )

    prompt_size = len(system_prompt) + len(user_prompt)
    if prompt_size > MAX_PROMPT_CHARS:
        last_cmd = history[-1]["command"] if history else "(none)"
        truncated_history = format_history(history[-3:], int(MAX_PROMPT_CHARS * 0.4))
        msg = (
            f"Prompt too large ({prompt_size} chars > limit {MAX_PROMPT_CHARS}). "
            "Refine to a smaller, targeted command (e.g., tail/head/grep with limits) instead of broad output."
        )
        log(msg=msg, prefix="WORKER PROMPT LIMIT")

        user_prompt = (
            f"GOAL:\n{goal}\n\n"
            "The last command produced too much output for the prompt budget. "
            f"Last command: {last_cmd}.\n"
            f"WORKER_MAX_PROMPT_CHARS={MAX_PROMPT_CHARS}.\n"
            "Provide a smaller, filtered command that returns limited output (e.g., tail -n 200, head, grep -m).\n"
            "Here is a truncated recent history:\n"
            f"{truncated_history}\n"
            "Return exactly one concise command and avoid re-emitting huge outputs."
        )

    # Log outgoing request
    log(
        msg=f"SYSTEM PROMPT:\n{system_prompt}\n\nUSER PROMPT:\n{user_prompt}",
        prefix="WORKER REQUEST",
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    # Log raw response
    log(
        msg=f"RAW RESPONSE:\n{response}",
        prefix="WORKER RAW RESPONSE",
    )

    content = response.choices[0].message.content.strip()

    # Log parsed JSON content
    log(
        msg=f"PARSED CONTENT:\n{content}",
        prefix="WORKER PARSED",
    )

    return json.loads(content)


def handle_ask_human(ask: dict, history: list) -> None:

    log(f"AGENT REQUESTED HUMAN INPUT:\n{ask}")

    """
    Process an ask_human request:
      - Prompt the user (unless already present in env).
      - Save the secret.
      - Reload .env to sync new secrets into the Python process.
      - Confirm the env var exists.
      - Append a CONFIRM_SECRET or CONFIRM_SECRET_FAILED step to history.
    """
    question = ask.get("question", "The agent requests a secret value.")
    key_name = ask.get("key_name", "SECRET_KEY")
    storage = ask.get("storage", "env")

    print("\n===================================")
    print("[AGENT REQUESTS HUMAN INPUT]")
    print(question)
    print(f"Expected environment variable name: {key_name} (storage: {storage})")
    print("Your input will be hidden as you type, if needed.")
    print("===================================\n")

    existing = os.environ.get(key_name)

    if existing:
        print(f"[INFO] Environment variable {key_name} is already set. Skipping prompt.")
    else:
        value = getpass(f"Enter value for {key_name}: ")
        save_secret(key_name, value, storage)

        # NEW: Reload .env to pull the new secret into this Python process
        load_dotenv(override=True)

    # Verification: confirm that environment variable exists and is non-empty
    confirmed_value = os.environ.get(key_name)

    if confirmed_value:
        print(f"[INFO] Verified that {key_name} is present in environment.")
        log(f"SECRET CONFIRMED: {key_name}")
        history.append(
            {
                "command": f"CONFIRM_SECRET {key_name}",
                "stdout": f"Secret {key_name} is present in environment.",
                "stderr": "",
                "returncode": 0,
            }
        )
    else:
        print(f"[ERROR] {key_name} is NOT present in environment after human input.")
        log(f"SECRET CONFIRMATION FAILED: {key_name}")
        history.append(
            {
                "command": f"CONFIRM_SECRET_FAILED {key_name}",
                "stdout": "",
                "stderr": f"Secret {key_name} is NOT present in environment.",
                "returncode": 1,
            }
        )


def request_human_intervention(message: str, history: list, tag: str = "NEEDS_HUMAN") -> None:
    print("\n===================================")
    print("[AGENT REQUESTS HUMAN INTERVENTION]")
    print(message)
    print("===================================\n")
    history.append(
        {
            "command": tag,
            "stdout": message,
            "stderr": "",
            "returncode": -2,
        }
    )


def verify_project_spec_access(project_path: str):
    data = load_project_spec(project_path)
    summary = summarize_project_spec(data)
    print(f"[WORKER] Project spec summary: {summary}")


def _needs_human_for_auth(stderr: str, stdout: str) -> tuple[bool, str]:
    combined = f"{stderr}\n{stdout}".lower()
    auth_indicators = [
        "authentication error",
        "permission denied",
        "not authorized",
        "403",
        "code: 10000",
        "request to the cloudflare api",
    ]
    for marker in auth_indicators:
        if marker in combined:
            return True, f"Authentication/permission issue detected: {marker}"
    return False, ""


def run_worker(goal: str, workdir: str | None = None, session_id: str | None = None):
    """
    Run the Worker agent for a given goal.

    Args:
        goal: The natural-language step description for the Worker.
        workdir: Directory in which all shell commands should execute.

    Returns:
        history: list of dicts describing each executed command.
    """
    history = []
    base_dir = workdir or os.getcwd()

    for step in range(30):  # safety limit
        try:
            llm_output = call_llm(goal, history, session_id=session_id)
        except JSONDecodeError as e:
            msg = (
                f"Model returned invalid JSON: {e}. Please re-emit valid JSON only, "
                "with keys command/done/thoughts (plus optional ask_human/needs_human)."
            )
            log(msg=msg, prefix="WORKER PARSE ERROR")
            history.append(
                {
                    "command": "PARSE_ERROR",
                    "stdout": "",
                    "stderr": msg,
                    "returncode": -1,
                }
            )
            print(msg)
            continue
        except Exception as e:
            log(msg=f"Worker halted due to error: {e}", prefix="WORKER ERROR")
            history.append(
                {
                    "command": "PAUSE_FOR_HUMAN",
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": -1,
                }
            )
            print("Worker paused for human intervention due to error:", e)
            break

        # Check if the model is asking for human input
        ask = llm_output.get("ask_human")
        if ask:
            handle_ask_human(ask, history)
            # Do NOT run any shell command this cycle
            continue

        needs_human = llm_output.get("needs_human")
        if needs_human:
            reason = needs_human.get("reason", "Human input required.")
            log(msg=f"Worker requested human intervention: {reason}", prefix="WORKER HUMAN NEEDED")
            history.append(
                {
                    "command": "PAUSE_FOR_HUMAN",
                    "stdout": "Human intervention requested. Reason: " + reason,
                    "stderr": "",
                    "returncode": -2,
                }
            )
            print("Worker paused for human intervention:", reason)
            break

        command = llm_output.get("command", "")
        done = llm_output.get("done", False)

        print("\n===============================")
        print("LLM Thoughts:", llm_output.get("thoughts", ""))
        print("Next command:", command)
        print("Done:", done)
        print("===============================\n")

        if command == "":
            print("Agent finished (no further command).")
            break

        result = run_shell(command, workdir=base_dir)
        print("Command output:")
        print(result["stdout"])
        print(result["stderr"])

        history.append(result)

        if result["returncode"] != 0:
            needs_human, reason = _needs_human_for_auth(result.get("stderr", ""), result.get("stdout", ""))
            if needs_human:
                log(msg=reason, prefix="WORKER HUMAN REQUIRED")
                request_human_intervention(reason, history, tag="NEEDS_HUMAN_AUTH")
                break

            fiction_msg = (
                "The last instruction was not verifiably true (non-zero exit). "
                "High probability of hallucination or partial info. Re-think and simplify to a testable step."
            )
            log(msg=fiction_msg, prefix="WORKER FICTION")
            history.append(
                {
                    "command": "FICTION_DETECTED",
                    "stdout": fiction_msg,
                    "stderr": "",
                    "returncode": result["returncode"],
                }
            )
            print(fiction_msg)
            continue

        if done:
            print("Agent finished (after executing final command).")
            break

    return history

def main():
    goal = input("Enter agent goal: ")
    run_worker(goal)


if __name__ == "__main__":
    main()
