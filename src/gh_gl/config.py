"""Manage the gh-gl config file (~/.config/gh-gl/config.toml)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "gh-gl"


def config_path() -> Path:
    return _config_dir() / "config.toml"


def load() -> dict[str, Any]:
    p = config_path()
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text())


def save(data: dict[str, Any]) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(tomli_w.dumps(data))


def get_project(name: Optional[str] = None) -> dict[str, Any]:
    """Return config for a project by name, or try to detect from cwd."""
    cfg = load()
    projects: dict[str, Any] = cfg.get("projects", {})

    if name:
        if name not in projects:
            raise SystemExit(f"Project '{name}' not found in config. Run 'gh-gl init' first.")
        return projects[name]

    # Auto-detect from git remote
    from gh_gl.shell import out, run
    import subprocess

    try:
        remotes_raw = out(["git", "remote", "-v"], quiet=True)
    except subprocess.CalledProcessError:
        raise SystemExit("Not in a git repository. Specify --project or cd into your repo.")

    for proj_name, proj in projects.items():
        gl_url = proj.get("gitlab_url", "")
        gh_url = proj.get("github_url", "")
        if gl_url in remotes_raw or gh_url in remotes_raw:
            return proj

    raise SystemExit(
        "Could not detect project from git remotes.\n"
        "Run 'gh-gl init' or specify --project NAME."
    )
