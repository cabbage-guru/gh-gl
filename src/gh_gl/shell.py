"""Run external commands (git, gh, glab) with consistent error handling."""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Optional

from rich.console import Console

err = Console(stderr=True)


def run(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    cwd: Optional[str] = None,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and return the result.

    By default stdout/stderr are captured and the return code is checked.
    """
    if not quiet:
        err.print(f"[dim]$ {shlex.join(cmd)}[/dim]")
    try:
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            cwd=cwd,
        )
    except FileNotFoundError:
        err.print(f"[red]Command not found:[/red] {cmd[0]}")
        err.print(f"Please install {cmd[0]} and make sure it's on your PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        if not quiet:
            if exc.stdout:
                err.print(exc.stdout.rstrip())
            if exc.stderr:
                err.print(f"[red]{exc.stderr.rstrip()}[/red]")
        raise


def run_ok(cmd: list[str], **kwargs) -> bool:
    """Return True if *cmd* exits 0, False otherwise. Never raises."""
    try:
        run(cmd, check=True, quiet=True, **kwargs)
        return True
    except subprocess.CalledProcessError:
        return False


def out(cmd: list[str], **kwargs) -> str:
    """Run *cmd* and return stripped stdout."""
    return run(cmd, **kwargs).stdout.strip()
