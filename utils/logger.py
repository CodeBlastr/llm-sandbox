import datetime
import os
from pathlib import Path


def _resolve_log_dir() -> Path:
    """Resolve the log directory from env (LOG_DIR) or default to ./logs."""
    env_dir = os.getenv("LOG_DIR")
    path = Path(env_dir) if env_dir else Path("logs")
    path.mkdir(parents=True, exist_ok=True)
    return path

def log(msg: str, *, prefix: str = "") -> None:
    """
    Append a timestamped log entry to today's agent log file.

    - msg: the text to log
    - prefix: optional tag like "PLANNER REQUEST" or "WORKER RESPONSE"
    """
    log_dir = _resolve_log_dir()
    timestamp = datetime.datetime.utcnow().isoformat()
    log_file = log_dir / datetime.datetime.utcnow().strftime("agent-%Y%m%d.log")

    with open(log_file, "a") as f:
        if prefix:
            f.write(f"[{timestamp}] [{prefix}] {msg}\n\n")
        else:
            f.write(f"[{timestamp}] {msg}\n\n")
