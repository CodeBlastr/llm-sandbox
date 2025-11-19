import datetime
from pathlib import Path

# Ensure logs directory exists at project root
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def log(msg: str, *, prefix: str = "") -> None:
    """
    Append a timestamped log entry to today's agent log file.

    - msg: the text to log
    - prefix: optional tag like "PLANNER REQUEST" or "WORKER RESPONSE"
    """
    timestamp = datetime.datetime.utcnow().isoformat()
    log_file = LOG_DIR / datetime.datetime.utcnow().strftime("agent-%Y%m%d.log")

    with open(log_file, "a") as f:
        if prefix:
            f.write(f"[{timestamp}] [{prefix}] {msg}\n\n")
        else:
            f.write(f"[{timestamp}] {msg}\n\n")
