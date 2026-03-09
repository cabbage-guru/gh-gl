"""GitLab CLI (glab) wrappers."""

from __future__ import annotations

import json
import subprocess
import urllib.parse

from gh_gl.shell import out, run, run_ok


def is_authenticated(hostname: str | None = None) -> bool:
    cmd = ["glab", "auth", "status"]
    if hostname:
        cmd += ["--hostname", hostname]
    return run_ok(cmd)


def extract_project_path(url: str) -> str:
    """Extract 'group/project' from a GitLab URL."""
    # Handle SSH urls: git@gitlab.example.com:group/project.git
    if url.startswith("git@"):
        path = url.split(":", 1)[1]
        return path.removesuffix(".git")
    # Handle HTTPS urls
    parsed = urllib.parse.urlparse(url)
    return parsed.path.strip("/").removesuffix(".git")


def extract_hostname(url: str) -> str:
    """Extract hostname from a GitLab URL."""
    if url.startswith("git@"):
        return url.split("@", 1)[1].split(":", 1)[0]
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname or ""


def create_mr(
    *,
    project_path: str,
    hostname: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str = "",
) -> str:
    """Create a merge request and return its URL."""
    cmd = [
        "glab", "mr", "create",
        "--repo", f"https://{hostname}/{project_path}",
        "--source-branch", source_branch,
        "--target-branch", target_branch,
        "--title", title,
        "--fill",
    ]
    if description:
        cmd += ["--description", description]

    result = out(cmd)
    # glab prints the MR url on the last line
    for line in result.splitlines():
        if "http" in line:
            return line.strip()
    return result


def list_mrs(
    project_path: str,
    hostname: str,
    state: str = "opened",
) -> list[dict]:
    """List merge requests."""
    result = out([
        "glab", "api",
        f"/projects/{urllib.parse.quote(project_path, safe='')}/merge_requests",
        "--hostname", hostname,
        "-X", "GET",
        "-f", f"state={state}",
        "-f", "per_page=20",
    ], quiet=True)
    return json.loads(result)
