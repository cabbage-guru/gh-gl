"""Git helper operations."""

from __future__ import annotations

import subprocess
from typing import Optional

from gh_gl.shell import out, run, run_ok


def current_branch(cwd: Optional[str] = None) -> str:
    return out(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, quiet=True)


def default_branch(remote: str = "origin", cwd: Optional[str] = None) -> str:
    """Detect the default branch of a remote."""
    try:
        ref = out(
            ["git", "symbolic-ref", f"refs/remotes/{remote}/HEAD"],
            cwd=cwd,
            quiet=True,
        )
        return ref.rsplit("/", 1)[-1]
    except subprocess.CalledProcessError:
        # Fallback: try fetching then check again
        run(["git", "remote", "set-head", remote, "--auto"], cwd=cwd, quiet=True)
        ref = out(
            ["git", "symbolic-ref", f"refs/remotes/{remote}/HEAD"],
            cwd=cwd,
            quiet=True,
        )
        return ref.rsplit("/", 1)[-1]


def list_remote_branches(remote: str, cwd: Optional[str] = None) -> list[str]:
    raw = out(["git", "branch", "-r", "--list", f"{remote}/*"], cwd=cwd, quiet=True)
    branches = []
    for line in raw.splitlines():
        line = line.strip()
        if " -> " in line:
            continue
        if line.startswith(f"{remote}/"):
            branches.append(line[len(remote) + 1 :])
    return branches


def list_local_branches(cwd: Optional[str] = None) -> list[str]:
    raw = out(["git", "branch", "--list"], cwd=cwd, quiet=True)
    return [line.strip().lstrip("* ") for line in raw.splitlines() if line.strip()]


def remote_url(remote: str, cwd: Optional[str] = None) -> str:
    return out(["git", "remote", "get-url", remote], cwd=cwd, quiet=True)


def has_remote(name: str, cwd: Optional[str] = None) -> bool:
    return run_ok(["git", "remote", "get-url", name], cwd=cwd)


def fetch(remote: str, cwd: Optional[str] = None) -> None:
    run(["git", "fetch", remote, "--prune"], cwd=cwd)


def add_remote(name: str, url: str, cwd: Optional[str] = None) -> None:
    run(["git", "remote", "add", name, url], cwd=cwd)


def set_remote_url(name: str, url: str, cwd: Optional[str] = None) -> None:
    run(["git", "remote", "set-url", name, url], cwd=cwd)
