import os
from dotenv import load_dotenv
from openai import OpenAI

from utils.logger import log


load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
CHEAP_MODEL = os.getenv("OPENAI_CHEAP_MODEL", "gpt-4o-mini")


def classify_task(prompt: str) -> str:
    """
    Lightweight task classification into: simple, medium, complex.

    Uses a cheap model and short context to avoid overhead before orchestration.
    """
    truncated_prompt = (prompt or "")[:500]
    system_prompt = (
        "Classify the requested software task into one of: simple, medium, complex.\n"
        "Return exactly one word: simple, medium, or complex.\n"
        "Guidance: simple = single file or small standalone deliverable; "
        "medium = multiple files, integrations, or tests; "
        "complex = multi-service, deployment, or CI/CD scale."
    )

    try:
        response = client.chat.completions.create(
            model=CHEAP_MODEL,
            temperature=0,
            max_tokens=4,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncated_prompt},
            ],
        )
        label = (response.choices[0].message.content or "").strip().lower().strip("\"'` ")
    except Exception as e:
        log(msg=f"Task classification failed ({e}); defaulting to 'medium'", prefix="CLASSIFIER ERROR")
        return "medium"

    if label not in {"simple", "medium", "complex"}:
        log(msg=f"Unexpected classification '{label}', defaulting to 'medium'", prefix="CLASSIFIER WARN")
        return "medium"

    log(msg=f"Task classified as '{label}' using {CHEAP_MODEL}", prefix="CLASSIFIER RESULT")
    return label


__all__ = ["classify_task"]
