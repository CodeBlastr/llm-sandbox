import os
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import log


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")

SYSTEM_PROMPT = """
You are the CTO / Planner agent.

Your job is to take a high-level business or engineering goal and break it down
into an ordered set of technical steps that a Worker agent can execute.

You NEVER write code or shell commands. You only produce STRUCTURED JSON
describing the plan.

The output JSON MUST have this format:

{
  "goal": "<restated high-level goal>",
  "steps": [
    { "id": 1, "description": "<detailed step>" },
    { "id": 2, "description": "<detailed step>" },
    ...
  ]
}

Rules:
- Steps must be specific enough for an executor agent to run without ambiguity.
- You do NOT decide secrets or API keys. If a Worker needs a secret, note it in the
  description, but do NOT ask for one.
- You do NOT perform any actions yourself.
- You do NOT reason about tools. You only plan.
- You do NOT output code, bash commands, or file content.
- Always restate the goal clearly in the "goal" field.
"""

def plan(goal: str) -> str:
    """
    Call the Planner agent to produce a structured plan.

    Returns:
        A JSON string representing the plan.
    """
    # Log outgoing request (system + user)
    log(
        msg=f"SYSTEM PROMPT:\n{SYSTEM_PROMPT}\n\nUSER GOAL:\n{goal}",
        prefix="PLANNER REQUEST"
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": goal}
        ]
    )

    # Log raw response object
    log(
        msg=f"RAW RESPONSE:\n{response}",
        prefix="PLANNER RAW RESPONSE"
    )

    content = response.choices[0].message.content.strip()

    # Log parsed content (what we actually return)
    log(
        msg=f"PARSED CONTENT:\n{content}",
        prefix="PLANNER PARSED"
    )

    return content


def main():
    goal = input("Enter high-level goal for Planner: ")
    plan_json = plan(goal)
    print("\n=== PLANNER OUTPUT ===")
    print(plan_json)
    print("======================")

if __name__ == "__main__":
    main()
