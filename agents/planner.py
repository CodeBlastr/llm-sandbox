import os
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import log
from utils.memory import summarize_recent_projects
from utils.campaign import load_campaign, summarize_campaign


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
    memory_context = summarize_recent_projects(goal)
    if memory_context:
        log(msg=f"Memory context injected:\n{memory_context}", prefix="PLANNER MEMORY")

    # Campaign context (if a campaign.yaml exists alongside the goal path)
    campaign_path = os.getenv("CAMPAIGN_PATH")
    campaign_context = ""
    if campaign_path:
        campaign_data = load_campaign(campaign_path)
        campaign_context = summarize_campaign(campaign_data)
        if campaign_context:
            log(msg=f"Campaign context injected:\n{campaign_context}", prefix="PLANNER CAMPAIGN")

    user_goal = goal
    if memory_context:
        user_goal = f"{goal}\n\nRelevant prior runs:\n{memory_context}"
    if campaign_context:
        user_goal = f"{user_goal}\n\nCampaign context:\n{campaign_context}"

    log(
        msg=f"SYSTEM PROMPT:\n{SYSTEM_PROMPT}\n\nUSER GOAL:\n{user_goal}",
        prefix="PLANNER REQUEST"
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_goal}
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


def verify_campaign_access(campaign_path: str):
    data = load_campaign(campaign_path)
    summary = summarize_campaign(data)
    print(f"[PLANNER] Campaign summary: {summary}")


def main():
    goal = input("Enter high-level goal for Planner: ")
    plan_json = plan(goal)
    print("\n=== PLANNER OUTPUT ===")
    print(plan_json)
    print("======================")

if __name__ == "__main__":
    main()
