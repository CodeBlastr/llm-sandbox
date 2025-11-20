import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import log

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")

SYSTEM_PROMPT = """
You are the Reviewer agent.

Your job is to REVIEW the work performed by the Planner and Worker agents.

You are GIVEN:
- A high-level goal.
- The Planner's JSON plan (if available).
- A textual summary of what the Worker actually did (commands, outputs, errors).

You MUST output a JSON object with this exact shape:

{
  "overall_assessment": "<short summary sentence of how well the work matched the goal>",
  "issues": [
    {
      "type": "<category, e.g. 'correctness', 'completeness', 'safety', 'style'>",
      "description": "<what is wrong or risky>",
      "severity": "<one of: 'low', 'medium', 'high'>"
    }
  ],
  "suggestions": [
    "<concrete suggestion for what the Worker should do next or fix>"
  ]
}

Rules:
- Do NOT invent details that are not implied by the input.
- If the plan or execution summary is missing or empty, say so clearly.
- If the work looks good, still provide at least one suggestion for improvement or validation.
- Be concise but specific.
- You NEVER output anything except the JSON object described above.
"""


def review(goal: str, planner_json: str | None, execution_summary: str) -> str:
    """
    Call the Reviewer agent.

    Args:
        goal: High-level goal as a string.
        planner_json: JSON string of the planner's output (may be None or empty).
        execution_summary: Text summary of worker's actions / history.

    Returns:
        A JSON string with the review.
    """
    user_payload = {
        "goal": goal,
        "planner_json": planner_json or "",
        "execution_summary": execution_summary,
    }

    user_content = json.dumps(user_payload, indent=2)

    # Log outgoing review request
    log(
        msg=f"REVIEW REQUEST PAYLOAD:\n{user_content}",
        prefix="REVIEWER REQUEST",
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    # Log raw response
    log(
        msg=f"RAW RESPONSE:\n{response}",
        prefix="REVIEWER RAW RESPONSE",
    )

    content = response.choices[0].message.content.strip()

    # Log parsed content (still a JSON string from the model)
    log(
        msg=f"PARSED CONTENT:\n{content}",
        prefix="REVIEWER PARSED",
    )

    return content


def main():
    """
    Simple CLI harness to test the Reviewer agent manually.
    """
    print("Reviewer agent test harness.")
    goal = input("Enter goal: ").strip()
    planner_json = input("Enter planner JSON (or leave blank): ").strip()
    print("Enter execution summary (end with CTRL+D):")

    # Read multiline execution summary from stdin
    try:
        execution_summary = ""
        while True:
            line = input()
            execution_summary += line + "\n"
    except EOFError:
        pass

    review_json = review(goal, planner_json or None, execution_summary)
    print("\n=== REVIEWER OUTPUT ===")
    print(review_json)
    print("========================")


if __name__ == "__main__":
    main()
