import os
import subprocess
import json
from getpass import getpass
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import log

# Load .env values into the environment (including any secrets you already put there)
load_dotenv(override=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")


def run_shell(command: str, workdir: str | None = None) -> dict:
    """Execute a shell command and capture output."""
    try:
        # Explicitly pass current environment (including secrets)
        env = os.environ.copy()

        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir or os.getcwd(),
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
    return (
        "You are an autonomous software engineer with access to a bash shell.\n"
        "You respond ONLY with valid JSON. The JSON MUST have these keys:\n"
        "  - command: string (the shell command to run, or \"\" if none)\n"
        "  - done: boolean (true if the overall goal is achieved)\n"
        "  - thoughts: string (your reasoning, for the human to read)\n"
        "You MAY also include an optional key:\n"
        "  - ask_human: object with keys {question: string, key_name: string, storage: string}\n"
        "\n"
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


def call_llm(goal: str, history: list) -> dict:
    """Send goal + history to the LLM and get the next action."""
    system_prompt = build_system_prompt()

    history_text = ""
    for step in history:
        history_text += (
            f"COMMAND: {step['command']}\n"
            f"RETURN CODE: {step['returncode']}\n"
            f"STDOUT:\n{step['stdout']}\n"
            f"STDERR:\n{step['stderr']}\n\n"
        )

    user_prompt = (
        f"GOAL:\n{goal}\n\n"
        f"HISTORY:\n{history_text}\n"
        "Decide what to do next. Either:\n"
        "  - Provide the next shell command in 'command', or\n"
        "  - If you cannot proceed without human-provided secrets, use 'ask_human'.\n"
        "The controller will verify that requested secrets exist as environment\n"
        "variables before proceeding."
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

        print(f"[ERROR] {key_name} is NOT present in environment after human input.")
        history.append(
            {
                "command": f"CONFIRM_SECRET_FAILED {key_name}",
                "stdout": "",
                "stderr": f"Secret {key_name} is NOT present in environment.",
                "returncode": 1,
            }
        )


def run_worker(goal: str, workdir: str | None = None):
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
        llm_output = call_llm(goal, history)

        # Check if the model is asking for human input
        ask = llm_output.get("ask_human")
        if ask:
            handle_ask_human(ask, history)
            # Do NOT run any shell command this cycle
            continue

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

        if done:
            print("Agent finished (after executing final command).")
            break

    return history

def main():
    goal = input("Enter agent goal: ")
    run_worker(goal)


if __name__ == "__main__":
    main()
