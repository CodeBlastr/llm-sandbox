import json
import os
import re
from fnmatch import fnmatch
from typing import Any


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _parse_list_env(name: str, default: list[str]) -> list[str]:
    if name not in os.environ:
        return default
    raw = os.getenv(name, "")
    if not raw.strip():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _normalize_patterns(patterns: list[str]) -> list[str]:
    return [_normalize_path(pat) for pat in patterns]


def _expand_allowlist_patterns(patterns: list[str], project_id: str) -> list[str]:
    return [pattern.replace("<project_id>", project_id) for pattern in patterns]


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _build_gate_config(project_id: str) -> dict[str, Any]:
    default_allowlist = [f"projects/{project_id}/**"]
    default_block_paths = [
        "**/.env",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
        "**/id_rsa",
        "**/id_ed25519",
    ]
    default_block_patterns = [
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ]

    allowlist_enabled = _parse_bool_env("RDM_MERGE_ALLOWLIST_ENABLED", True)
    allowlist = _parse_list_env("RDM_MERGE_ALLOWLIST", default_allowlist)
    hard_stop_paths = _parse_list_env("RDM_MERGE_HARD_STOP_PATHS", default_block_paths)
    hard_stop_patterns = _parse_list_env("RDM_MERGE_HARD_STOP_PATTERNS", default_block_patterns)

    max_files = _parse_int_env("RDM_MERGE_MAX_FILES", 25)
    max_additions = _parse_int_env("RDM_MERGE_MAX_ADD_LINES", 500)
    max_deletions = _parse_int_env("RDM_MERGE_MAX_DELETE_LINES", 500)

    return {
        "allowlist_enabled": allowlist_enabled,
        "allowlist": _expand_allowlist_patterns(_normalize_patterns(allowlist), project_id),
        "hard_stop_paths": _normalize_patterns(hard_stop_paths),
        "hard_stop_patterns": hard_stop_patterns,
        "max_files": max_files,
        "max_additions": max_additions,
        "max_deletions": max_deletions,
    }


def evaluate_merge_gate(
    project_id: str,
    file_paths: list[str],
    diff_text: str,
    additions: int,
    deletions: int,
    binary_files: list[str] | None = None,
) -> dict[str, Any]:
    config = _build_gate_config(project_id)
    violations = {"block": [], "manual": []}
    reasons: list[str] = []

    normalized_paths = [_normalize_path(path) for path in file_paths]

    if config["allowlist_enabled"]:
        for path in normalized_paths:
            if not _matches_any(path, config["allowlist"]):
                violations["manual"].append(f"Path not in allowlist: {path}")

    for path in normalized_paths:
        scoped = f"projects/{project_id}/{path}"
        if _matches_any(path, config["hard_stop_paths"]) or _matches_any(scoped, config["hard_stop_paths"]):
            violations["block"].append(f"Hard-stop path matched: {path}")

    file_count = len(normalized_paths)
    if file_count > config["max_files"]:
        violations["manual"].append(f"File count {file_count} exceeds max {config['max_files']}")

    if additions > config["max_additions"]:
        violations["manual"].append(f"Additions {additions} exceeds max {config['max_additions']}")

    if deletions > config["max_deletions"]:
        violations["manual"].append(f"Deletions {deletions} exceeds max {config['max_deletions']}")

    if binary_files:
        for path in binary_files:
            violations["manual"].append(f"Binary file change requires manual review: {path}")

    for pattern in config["hard_stop_patterns"]:
        try:
            if re.search(pattern, diff_text, flags=re.MULTILINE):
                violations["block"].append(f"Hard-stop pattern matched: {pattern}")
        except re.error:
            violations["manual"].append(f"Invalid hard-stop pattern: {pattern}")

    if violations["block"]:
        decision = "block"
        reasons.extend(violations["block"])
    elif violations["manual"]:
        decision = "manual_required"
        reasons.extend(violations["manual"])
    else:
        decision = "auto_merge_ok"

    eligible = decision == "auto_merge_ok"
    report = {
        "decision": decision,
        "eligible": eligible,
        "reasons": reasons,
        "violations": violations,
        "stats": {
            "files_changed": file_count,
            "additions": additions,
            "deletions": deletions,
        },
        "config": {
            "allowlist_enabled": config["allowlist_enabled"],
            "allowlist": config["allowlist"],
            "hard_stop_paths": config["hard_stop_paths"],
            "hard_stop_patterns": config["hard_stop_patterns"],
            "max_files": config["max_files"],
            "max_additions": config["max_additions"],
            "max_deletions": config["max_deletions"],
        },
    }

    return report


def format_gate_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=False)


def _sanity_check_allowlist() -> dict[str, str]:
    project_id = "sample"
    prev_allowlist = os.environ.get("RDM_MERGE_ALLOWLIST")
    prev_enabled = os.environ.get("RDM_MERGE_ALLOWLIST_ENABLED")

    os.environ["RDM_MERGE_ALLOWLIST"] = "projects/<project_id>/**"
    os.environ["RDM_MERGE_ALLOWLIST_ENABLED"] = "true"

    try:
        outside = evaluate_merge_gate(
            project_id=project_id,
            file_paths=["utils/github_publisher.py"],
            diff_text="",
            additions=0,
            deletions=0,
        )
        inside = evaluate_merge_gate(
            project_id=project_id,
            file_paths=[f"projects/{project_id}/foo.txt"],
            diff_text="",
            additions=0,
            deletions=0,
        )
        return {
            "outside_decision": outside.get("decision", ""),
            "inside_decision": inside.get("decision", ""),
        }
    finally:
        if prev_allowlist is None:
            os.environ.pop("RDM_MERGE_ALLOWLIST", None)
        else:
            os.environ["RDM_MERGE_ALLOWLIST"] = prev_allowlist

        if prev_enabled is None:
            os.environ.pop("RDM_MERGE_ALLOWLIST_ENABLED", None)
        else:
            os.environ["RDM_MERGE_ALLOWLIST_ENABLED"] = prev_enabled


if __name__ == "__main__":
    results = _sanity_check_allowlist()
    print("Merge gate allowlist sanity check:")
    print(f"- utils/github_publisher.py decision: {results['outside_decision']}")
    print(f"- projects/<id>/foo.txt decision: {results['inside_decision']}")


__all__ = ["evaluate_merge_gate", "format_gate_report"]
