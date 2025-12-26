import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from utils.github_client import GitHubClientError, create_pull_request, get_repo_info, merge_pull_request
from utils.logger import log


def _run_git(args: list[str], project_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def _strip_git_suffix(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def _parse_github_remote(remote_url: str) -> tuple[str, str] | None:
    if remote_url.startswith("git@"):
        match = re.match(r"git@[^:]+:([^/]+)/(.+)$", remote_url)
        if not match:
            return None
        owner = match.group(1)
        repo = _strip_git_suffix(match.group(2))
        return owner, repo

    parsed = urlparse(remote_url)
    if not parsed.path:
        return None
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = _strip_git_suffix(parts[1])
    return owner, repo


def _to_https_url(remote_url: str) -> str | None:
    if remote_url.startswith("git@"):
        host_and_path = remote_url.split("@", 1)[1]
        if ":" not in host_and_path:
            return None
        host, path = host_and_path.split(":", 1)
        return f"https://{host}/{path}"
    if remote_url.startswith("ssh://git@"):
        parsed = urlparse(remote_url)
        if not parsed.hostname:
            return None
        return f"https://{parsed.hostname}{parsed.path}"
    return remote_url


def _build_authed_url(remote_url: str) -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None

    https_url = _to_https_url(remote_url)
    if not https_url:
        return None

    parsed = urlparse(https_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    if "@" in parsed.netloc:
        return https_url

    authed_netloc = f"x-access-token:{token}@{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=authed_netloc))


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = "step"
    return slug[:max_len]


def _short_goal(text: str, max_len: int = 60) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return "Update"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _resolve_approval_mode() -> tuple[str, str | None]:
    raw_value = os.getenv("RDM_PR_APPROVAL_MODE", "")
    normalized = raw_value.strip().lower()
    if normalized == "manual":
        return "manual", None
    if normalized in {"", "auto"}:
        return "auto", None
    return "auto", raw_value


def _build_branch_name(step_id: str, description: str, attempt_label: str) -> str:
    slug_source = description or "step"
    if attempt_label and attempt_label != "initial":
        slug_source = f"{slug_source}-{attempt_label}"
    slug = _slugify(slug_source, max_len=40)
    return f"rdm/step-{step_id}-{slug}"


def _summarize_commands(worker_history: list[dict]) -> list[str]:
    commands: list[str] = []
    for entry in worker_history:
        cmd = str(entry.get("command", "")).strip()
        if cmd:
            commands.append(cmd)
    return commands


def _build_pr_body(session_id: str | None, step_id: str, commands: list[str], files: list[str]) -> str:
    lines = [
        f"Session ID: {session_id or 'unknown'}",
        f"Step Number: {step_id}",
        "",
        "Commands:",
    ]

    if commands:
        lines.extend([f"- {cmd}" for cmd in commands])
    else:
        lines.append("- No commands recorded; step executed without shell commands.")

    lines.append("")
    lines.append("Files Changed:")
    if files:
        lines.extend([f"- {path}" for path in files])
    else:
        lines.append("- (none)")

    return "\n".join(lines)


def _step_succeeded(worker_history: list[dict]) -> bool:
    return all(entry.get("returncode", 1) == 0 for entry in worker_history)


def _format_merge_failure(status: int, data: dict) -> str:
    message = ""
    if isinstance(data, dict):
        message = str(data.get("message") or "").strip()
        errors = data.get("errors")
        if errors:
            error_parts: list[str] = []
            if isinstance(errors, list):
                for err in errors:
                    if isinstance(err, dict):
                        err_msg = err.get("message") or err.get("code") or str(err)
                    else:
                        err_msg = str(err)
                    if err_msg:
                        error_parts.append(err_msg)
            else:
                error_parts.append(str(errors))

            if error_parts:
                joined = "; ".join(error_parts)
                message = f"{message} ({joined})" if message else joined

    return message or f"merge failed (status {status})"


def publish_step_pr(
    project_dir: Path,
    step_id: int | str | None,
    description: str,
    worker_history: list[dict],
    session_id: str | None,
    attempt_label: str,
) -> dict:
    step_label = str(step_id) if step_id is not None else "unknown"
    mode, invalid_mode = _resolve_approval_mode()
    log(msg=f"RDM_PR_APPROVAL_MODE={mode}", prefix="ORCH PR")
    if invalid_mode:
        log(
            msg=f"Invalid RDM_PR_APPROVAL_MODE value '{invalid_mode}', defaulting to auto.",
            prefix="ORCH PR",
        )

    def _blocked(reason: str) -> dict:
        log(msg=f"merge_blocked: {reason}", prefix="ORCH PR")
        return {
            "status": "merge_blocked",
            "reason": reason,
            "should_stop": True,
            "step_id": step_label,
            "mode": mode,
        }

    if not _step_succeeded(worker_history):
        log(msg=f"Step {step_label} not successful; skipping PR", prefix="ORCH PR")
        return {
            "status": "skipped",
            "should_stop": False,
            "step_id": step_label,
            "mode": mode,
        }

    status = _run_git(["status", "--porcelain"], project_dir)
    if status.returncode != 0:
        return _blocked(f"Git status failed for step {step_label}: {status.stderr}")
    if not status.stdout.strip():
        log(msg=f"Step {step_label}: no changes, skipping PR", prefix="ORCH PR")
        return {
            "status": "no_changes",
            "should_stop": False,
            "step_id": step_label,
            "mode": mode,
        }

    add = _run_git(["add", "-A"], project_dir)
    if add.returncode != 0:
        return _blocked(f"Git add failed for step {step_label}: {add.stderr}")

    diff = _run_git(["diff", "--name-only", "--cached"], project_dir)
    if diff.returncode != 0:
        return _blocked(f"Git diff failed for step {step_label}: {diff.stderr}")
    files = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    if not files:
        log(msg=f"Step {step_label}: no changes, skipping PR", prefix="ORCH PR")
        return {
            "status": "no_changes",
            "should_stop": False,
            "step_id": step_label,
            "mode": mode,
        }

    title = f"RDM Step {step_label}: {_short_goal(description)}"
    commit = _run_git(["commit", "-m", title], project_dir)
    if commit.returncode != 0:
        return _blocked(f"Git commit failed for step {step_label}: {commit.stderr}")

    remote = _run_git(["remote", "get-url", "origin"], project_dir)
    if remote.returncode != 0:
        return _blocked(f"Git remote lookup failed for step {step_label}: {remote.stderr}")
    remote_url = remote.stdout.strip()

    owner_repo = _parse_github_remote(remote_url)
    if not owner_repo:
        return _blocked(f"Failed to parse GitHub remote for step {step_label}: {remote_url}")
    owner, repo = owner_repo

    branch = _build_branch_name(step_label, description, attempt_label)
    push_url = _build_authed_url(remote_url)
    if push_url:
        push = _run_git(["push", push_url, f"HEAD:refs/heads/{branch}"], project_dir)
    else:
        push = _run_git(["push", "origin", f"HEAD:refs/heads/{branch}"], project_dir)

    if push.returncode != 0:
        return _blocked(f"Git push failed for step {step_label}: {push.stderr}")

    try:
        repo_info = get_repo_info(owner, repo)
        base_branch = repo_info.get("default_branch") or "main"
        commands = _summarize_commands(worker_history)
        body = _build_pr_body(session_id, step_label, commands, files)
        pr = create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            head=branch,
            base=base_branch,
        )
    except GitHubClientError as e:
        message = str(e)
        if "already exists" in message.lower():
            return _blocked(f"PR already exists for {owner}/{repo} (branch {branch})")
        return _blocked(f"Failed to open PR for {owner}/{repo}: {e}")

    pr_url = pr.get("html_url")
    pr_number = pr.get("number")
    if pr_url:
        log(msg=f"Opened PR: {pr_url}", prefix="ORCH PR")
    elif pr_number:
        log(msg=f"Opened PR: {owner}/{repo}#{pr_number}", prefix="ORCH PR")
    else:
        log(msg=f"Opened PR for {owner}/{repo} (branch {branch})", prefix="ORCH PR")

    result = {
        "status": "pr_opened",
        "should_stop": False,
        "step_id": step_label,
        "mode": mode,
        "owner": owner,
        "repo": repo,
        "pr_url": pr_url,
        "pr_number": pr_number,
    }

    if mode == "manual":
        log(msg="awaiting_manual_approval", prefix="ORCH PR")
        result["status"] = "awaiting_manual_approval"
        result["should_stop"] = True
        return result

    if pr_number is None:
        return _blocked("Missing PR number from GitHub response.")

    try:
        merge_status, merge_data = merge_pull_request(owner, repo, int(pr_number), merge_method="merge")
    except GitHubClientError as e:
        return _blocked(f"Merge API error: {e}")

    if merge_status == 200 and merge_data.get("merged") is True:
        log(msg="merge_succeeded", prefix="ORCH PR")
        result["status"] = "merge_succeeded"
        return result

    reason = _format_merge_failure(merge_status, merge_data)
    return _blocked(reason)
