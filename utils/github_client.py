import json
import os
import urllib.error
import urllib.request


API_ROOT = "https://api.github.com"


class GitHubClientError(Exception):
    pass


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "rdm-engine",
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method, headers=_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8") if resp.length is None or resp.length > 0 else ""
            parsed = json.loads(body) if body else {}
            return resp.status, parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"message": body}
        return e.code, parsed
    except urllib.error.URLError as e:
        raise GitHubClientError(f"Network error contacting GitHub: {e}") from e


def _get_auth_user(token: str) -> str:
    status, data = _request("GET", f"{API_ROOT}/user", token)
    if status != 200:
        raise GitHubClientError(f"Failed to fetch authenticated user (status {status}): {data}")
    return data.get("login") or ""


def _get_repo(owner: str, name: str, token: str) -> dict | None:
    status, data = _request("GET", f"{API_ROOT}/repos/{owner}/{name}", token)
    if status == 200:
        return data
    if status == 404:
        return None
    raise GitHubClientError(f"Failed to check repo (status {status}): {data}")


def _create_repo(owner: str, name: str, token: str) -> dict:
    auth_login = _get_auth_user(token)
    if auth_login and auth_login.lower() == owner.lower():
        create_url = f"{API_ROOT}/user/repos"
    else:
        create_url = f"{API_ROOT}/orgs/{owner}/repos"

    payload = {"name": name, "private": True}
    status, data = _request("POST", create_url, token, payload)
    if status in {200, 201}:
        return data
    # If name already exists, fetch and return
    if status == 422:
        existing = _get_repo(owner, name, token)
        if existing:
            return existing
    raise GitHubClientError(f"Failed to create repo (status {status}): {data}")


def create_repo_if_missing(project_name: str) -> dict:
    """
    Ensure a private repo exists on GitHub for this project under GITHUB_OWNER.
    Returns a dict with at least: {"ssh_url": ..., "clone_url": ..., "html_url": ...}.
    Raises GitHubClientError on missing env or API errors.
    """
    token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    if not token or not owner:
        raise GitHubClientError("GITHUB_TOKEN or GITHUB_OWNER is missing from environment.")

    existing = _get_repo(owner, project_name, token)
    if existing:
        return existing

    return _create_repo(owner, project_name, token)


def get_repo_info(owner: str, name: str) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise GitHubClientError("GITHUB_TOKEN is missing from environment.")

    repo = _get_repo(owner, name, token)
    if repo:
        return repo
    raise GitHubClientError(f"Repo not found: {owner}/{name}")


def create_pull_request(owner: str, repo: str, title: str, body: str, head: str, base: str) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise GitHubClientError("GITHUB_TOKEN is missing from environment.")

    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    status, data = _request("POST", f"{API_ROOT}/repos/{owner}/{repo}/pulls", token, payload)
    if status in {200, 201}:
        return data
    raise GitHubClientError(f"Failed to create pull request (status {status}): {data}")


__all__ = [
    "create_repo_if_missing",
    "create_pull_request",
    "get_repo_info",
    "GitHubClientError",
]
