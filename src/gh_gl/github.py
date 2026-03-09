"""GitHub CLI (gh) wrappers."""

from __future__ import annotations

import json
import subprocess

from gh_gl.shell import out, run, run_ok


def is_authenticated() -> bool:
    return run_ok(["gh", "auth", "status"])


def repo_exists(owner: str, repo: str) -> bool:
    return run_ok(["gh", "repo", "view", f"{owner}/{repo}", "--json", "name"])


def create_private_repo(owner: str, repo: str) -> str:
    """Create a private repo and return its clone URL."""
    # gh repo create prints the URL to stdout; --json is not supported here
    out([
        "gh", "repo", "create", f"{owner}/{repo}",
        "--private",
    ])
    # Fetch the SSH URL from the newly created repo
    return get_repo_url(owner, repo)


def _git_protocol() -> str:
    """Return the git protocol configured in ``gh`` (ssh or https)."""
    try:
        proto = out(["gh", "config", "get", "git_protocol"], quiet=True).strip()
        if proto in ("ssh", "https"):
            return proto
    except subprocess.CalledProcessError:
        pass
    return "ssh"


def get_repo_url(owner: str, repo: str) -> str:
    """Return the clone URL for a GitHub repo, respecting ``gh`` protocol config."""
    proto = _git_protocol()
    field = "sshUrl" if proto == "ssh" else "url"
    result = out([
        "gh", "repo", "view", f"{owner}/{repo}",
        "--json", field,
    ], quiet=True)
    return json.loads(result)[field]


def delete_repo(owner: str, repo: str) -> None:
    run(["gh", "repo", "delete", f"{owner}/{repo}", "--yes"])


def list_prs(owner: str, repo: str, state: str = "open") -> list[dict]:
    result = out([
        "gh", "pr", "list",
        "--repo", f"{owner}/{repo}",
        "--state", state,
        "--json", "number,title,headRefName,state,url",
    ], quiet=True)
    return json.loads(result)
