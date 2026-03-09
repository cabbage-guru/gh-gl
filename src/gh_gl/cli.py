"""gh-gl: sync repositories between GitLab (authoritative) and GitHub (workspace)."""

from __future__ import annotations

import json
import subprocess
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from gh_gl import config, git, github, gitlab
from gh_gl.shell import out, run

console = Console()
err = Console(stderr=True)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _pick(prompt: str, choices: list[str], default: str | None = None) -> str:
    """Interactive single-select using rich."""
    if not choices:
        raise SystemExit("No choices available.")
    console.print(f"\n[bold]{prompt}[/bold]")
    for i, c in enumerate(choices, 1):
        marker = "[green]>[/green] " if c == default else "  "
        console.print(f"  {marker}{i}. {c}")
    while True:
        raw = Prompt.ask("Enter number", default="1")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        console.print("[red]Invalid choice, try again.[/red]")


# ── CLI group ────────────────────────────────────────────────────────────────


@click.group()
@click.option("--project", "-p", default=None, help="Project name from config.")
@click.pass_context
def main(ctx: click.Context, project: str | None) -> None:
    """gh-gl -- GitLab <-> GitHub repository sync.

    GitLab is authoritative. GitHub is a disposable private workspace
    for AI-assisted development.
    """
    ctx.ensure_object(dict)
    ctx.obj["project_name"] = project


# ── init ─────────────────────────────────────────────────────────────────────


@main.command()
@click.option("--gitlab-remote", default=None, help="GitLab remote name (default: auto-detect or 'origin').")
@click.option("--github-owner", default=None, help="GitHub owner/org for the mirror repo.")
@click.option("--github-repo", default=None, help="GitHub repo name (default: same as GitLab).")
@click.option("--name", default=None, help="Project name in gh-gl config.")
def init(
    gitlab_remote: str | None,
    github_owner: str | None,
    github_repo: str | None,
    name: str | None,
) -> None:
    """Initialize sync: link a GitLab repo to a private GitHub mirror."""
    console.print(Panel("[bold]gh-gl init[/bold] — set up GitLab ↔ GitHub sync", style="blue"))

    # ── Step 1: Verify tools ────────────────────────────────────────────
    _check_tools()

    # ── Step 2: Detect / ask for GitLab remote ──────────────────────────
    try:
        remotes_raw = out(["git", "remote", "-v"], quiet=True)
    except (subprocess.CalledProcessError, SystemExit):
        raise SystemExit("Not in a git repository. Run this from your GitLab checkout.")

    if gitlab_remote is None:
        gitlab_remote = "origin"
        console.print(f"Using GitLab remote: [cyan]{gitlab_remote}[/cyan]")

    gl_url = git.remote_url(gitlab_remote)
    gl_host = gitlab.extract_hostname(gl_url)
    gl_project = gitlab.extract_project_path(gl_url)
    console.print(f"  GitLab host:    [cyan]{gl_host}[/cyan]")
    console.print(f"  GitLab project: [cyan]{gl_project}[/cyan]")

    # ── Step 3: GitHub target ───────────────────────────────────────────
    if github_owner is None:
        # Try to get current gh user
        try:
            github_owner = out(["gh", "api", "user", "--jq", ".login"], quiet=True)
        except subprocess.CalledProcessError:
            github_owner = Prompt.ask("GitHub owner (user or org)")
    if github_repo is None:
        github_repo = gl_project.rsplit("/", 1)[-1]

    console.print(f"\n  GitHub target:  [cyan]{github_owner}/{github_repo}[/cyan] (private)")

    # ── Step 4: Create or verify GitHub repo ────────────────────────────
    if github.repo_exists(github_owner, github_repo):
        console.print("[yellow]GitHub repo already exists.[/yellow]")
        gh_url = github.get_repo_url(github_owner, github_repo)
    else:
        if not Confirm.ask(f"Create private GitHub repo [bold]{github_owner}/{github_repo}[/bold]?", default=True):
            raise SystemExit("Aborted.")
        gh_url = github.create_private_repo(github_owner, github_repo)
        console.print(f"[green]Created private repo:[/green] {gh_url}")

    # ── Step 5: Add github remote ───────────────────────────────────────
    gh_remote = "github"
    if git.has_remote(gh_remote):
        git.set_remote_url(gh_remote, gh_url)
        console.print(f"Updated remote [cyan]{gh_remote}[/cyan] → {gh_url}")
    else:
        git.add_remote(gh_remote, gh_url)
        console.print(f"Added remote [cyan]{gh_remote}[/cyan] → {gh_url}")

    # ── Step 6: Save config ─────────────────────────────────────────────
    proj_name = name or github_repo
    cfg = config.load()
    cfg.setdefault("projects", {})
    cfg["projects"][proj_name] = {
        "gitlab_url": gl_url,
        "gitlab_host": gl_host,
        "gitlab_project": gl_project,
        "gitlab_remote": gitlab_remote,
        "github_owner": github_owner,
        "github_repo": github_repo,
        "github_url": gh_url,
        "github_remote": gh_remote,
    }
    config.save(cfg)
    console.print(f"\n[green]Config saved to {config.config_path()}[/green]")

    # ── Step 7: Initial sync ────────────────────────────────────────────
    if Confirm.ask("Push all branches to GitHub now?", default=True):
        _do_sync(cfg["projects"][proj_name])

    console.print(Panel("[green bold]Init complete![/green bold] Run [cyan]gh-gl sync[/cyan] anytime to update.", style="green"))


# ── sync ─────────────────────────────────────────────────────────────────────


@main.command()
@click.option("--branches", "-b", default=None, help="Comma-separated branches to sync. Default: all.")
@click.pass_context
def sync(ctx: click.Context, branches: str | None) -> None:
    """Sync branches from GitLab to GitHub.

    Fetches from GitLab and pushes to the private GitHub mirror.
    """
    proj = config.get_project(ctx.obj["project_name"])
    console.print(Panel("[bold]gh-gl sync[/bold] — GitLab → GitHub", style="blue"))

    branch_list = [b.strip() for b in branches.split(",")] if branches else None
    _do_sync(proj, branch_filter=branch_list)
    console.print("[green]Sync complete.[/green]")


def _do_sync(proj: dict, branch_filter: list[str] | None = None) -> None:
    gl_remote = proj["gitlab_remote"]
    gh_remote = proj["github_remote"]

    console.print(f"Fetching from [cyan]{gl_remote}[/cyan] (GitLab)...")
    git.fetch(gl_remote)

    remote_branches = git.list_remote_branches(gl_remote)
    if branch_filter:
        remote_branches = [b for b in remote_branches if b in branch_filter]

    if not remote_branches:
        console.print("[yellow]No branches to sync.[/yellow]")
        return

    console.print(f"Pushing {len(remote_branches)} branch(es) to [cyan]{gh_remote}[/cyan] (GitHub)...")
    refspecs = [f"refs/remotes/{gl_remote}/{b}:refs/heads/{b}" for b in remote_branches]
    run(["git", "push", gh_remote, "--force"] + refspecs)

    # Also push tags
    run(["git", "push", gh_remote, "--tags", "--force"])


# ── push-branch ──────────────────────────────────────────────────────────────


@main.command("push-branch")
@click.argument("branch", required=False)
@click.option("--target", "-t", default=None, help="Target branch for MR (default: repo default branch).")
@click.option("--title", default=None, help="MR title.")
@click.option("--no-mr", is_flag=True, help="Just push the branch, don't create an MR.")
@click.pass_context
def push_branch(
    ctx: click.Context,
    branch: str | None,
    target: str | None,
    title: str | None,
    no_mr: bool,
) -> None:
    """Push a GitHub branch to GitLab and optionally create a merge request.

    If BRANCH is not specified, shows an interactive picker of GitHub branches
    that don't exist on GitLab yet.
    """
    proj = config.get_project(ctx.obj["project_name"])
    console.print(Panel("[bold]gh-gl push-branch[/bold] — GitHub → GitLab", style="blue"))

    gl_remote = proj["gitlab_remote"]
    gh_remote = proj["github_remote"]

    # Fetch both sides
    console.print("Fetching remotes...")
    git.fetch(gh_remote)
    git.fetch(gl_remote)

    gh_branches = set(git.list_remote_branches(gh_remote))
    gl_branches = set(git.list_remote_branches(gl_remote))

    # Determine which branch to push
    if branch is None:
        new_branches = sorted(gh_branches - gl_branches)
        if not new_branches:
            console.print("[yellow]No new branches on GitHub to push to GitLab.[/yellow]")
            console.print("All GitHub branches already exist on GitLab.")
            return
        branch = _pick("Select a branch to push to GitLab:", new_branches)

    if branch not in gh_branches:
        raise SystemExit(f"Branch '{branch}' not found on {gh_remote}.")

    console.print(f"\nPushing [cyan]{branch}[/cyan] to GitLab...")
    run(["git", "push", gl_remote, f"refs/remotes/{gh_remote}/{branch}:refs/heads/{branch}"])
    console.print(f"[green]Branch pushed to GitLab.[/green]")

    if no_mr:
        return

    # ── Create MR ───────────────────────────────────────────────────────
    if not Confirm.ask("Create a merge request on GitLab?", default=True):
        return

    if target is None:
        try:
            target = git.default_branch(gl_remote)
        except subprocess.CalledProcessError:
            target = Prompt.ask("Target branch for MR", default="main")

    if title is None:
        title = Prompt.ask("MR title", default=branch.replace("-", " ").replace("_", " ").title())

    description = Prompt.ask("MR description (optional)", default="")

    console.print(f"Creating MR: [cyan]{branch}[/cyan] → [cyan]{target}[/cyan]...")
    mr_url = gitlab.create_mr(
        project_path=proj["gitlab_project"],
        hostname=proj["gitlab_host"],
        source_branch=branch,
        target_branch=target,
        title=title,
        description=description,
    )
    console.print(f"\n[green bold]Merge request created:[/green bold] {mr_url}")


# ── status ───────────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show sync status: branches on each side, divergence info."""
    proj = config.get_project(ctx.obj["project_name"])
    console.print(Panel("[bold]gh-gl status[/bold]", style="blue"))

    gl_remote = proj["gitlab_remote"]
    gh_remote = proj["github_remote"]

    console.print("Fetching remotes...")
    git.fetch(gl_remote)
    git.fetch(gh_remote)

    gl_branches = set(git.list_remote_branches(gl_remote))
    gh_branches = set(git.list_remote_branches(gh_remote))
    all_branches = sorted(gl_branches | gh_branches)

    table = Table(title="Branch Status")
    table.add_column("Branch", style="cyan")
    table.add_column("GitLab", justify="center")
    table.add_column("GitHub", justify="center")
    table.add_column("Status")

    for b in all_branches:
        on_gl = b in gl_branches
        on_gh = b in gh_branches
        gl_mark = "[green]✓[/green]" if on_gl else "[dim]–[/dim]"
        gh_mark = "[green]✓[/green]" if on_gh else "[dim]–[/dim]"

        if on_gl and on_gh:
            # Check if they're the same commit
            gl_sha = out(
                ["git", "rev-parse", f"refs/remotes/{gl_remote}/{b}"],
                quiet=True,
            )
            gh_sha = out(
                ["git", "rev-parse", f"refs/remotes/{gh_remote}/{b}"],
                quiet=True,
            )
            if gl_sha == gh_sha:
                status_str = "[green]in sync[/green]"
            else:
                status_str = "[yellow]diverged[/yellow]"
        elif on_gl and not on_gh:
            status_str = "[dim]GitLab only (run sync)[/dim]"
        else:
            status_str = "[blue]GitHub only (push-branch?)[/blue]"

        table.add_row(b, gl_mark, gh_mark, status_str)

    console.print(table)

    # Summary
    only_gh = gh_branches - gl_branches
    if only_gh:
        console.print(
            f"\n[blue]{len(only_gh)}[/blue] branch(es) on GitHub only. "
            "Use [cyan]gh-gl push-branch[/cyan] to send them to GitLab."
        )


# ── nuke ─────────────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def nuke(ctx: click.Context) -> None:
    """Delete the GitHub mirror repo (GitHub is disposable!)."""
    proj = config.get_project(ctx.obj["project_name"])
    owner = proj["github_owner"]
    repo = proj["github_repo"]

    console.print(
        f"[red bold]This will permanently delete the GitHub repo "
        f"{owner}/{repo}![/red bold]\n"
        "This is safe because GitLab is the authoritative source."
    )

    if not Confirm.ask(f"Delete [red]{owner}/{repo}[/red] on GitHub?", default=False):
        console.print("Aborted.")
        return

    github.delete_repo(owner, repo)
    console.print(f"[green]Deleted {owner}/{repo} on GitHub.[/green]")

    # Clean up remote
    try:
        run(["git", "remote", "remove", proj["github_remote"]], quiet=True)
    except subprocess.CalledProcessError:
        pass

    # Remove from config
    cfg = config.load()
    for pname, p in list(cfg.get("projects", {}).items()):
        if p.get("github_owner") == owner and p.get("github_repo") == repo:
            del cfg["projects"][pname]
    config.save(cfg)
    console.print("[green]Cleaned up config.[/green]")


# ── config ───────────────────────────────────────────────────────────────────


@main.command("config")
def show_config() -> None:
    """Show the current configuration."""
    import pprint

    cfg = config.load()
    if not cfg:
        console.print("[yellow]No configuration found. Run [cyan]gh-gl init[/cyan] first.[/yellow]")
        return
    console.print(Panel(pprint.pformat(cfg), title="~/.config/gh-gl/config.toml", style="blue"))


# ── preflight ────────────────────────────────────────────────────────────────


def _check_tools() -> None:
    """Verify required CLI tools are installed and authenticated."""
    ok = True
    for tool, check in [
        ("git", ["git", "--version"]),
        ("gh", ["gh", "--version"]),
        ("glab", ["glab", "--version"]),
    ]:
        try:
            out(check, quiet=True)
            console.print(f"  [green]✓[/green] {tool}")
        except SystemExit:
            console.print(f"  [red]✗[/red] {tool} — not found")
            ok = False

    if not ok:
        raise SystemExit("Missing required tools. Install git, gh, and glab.")

    # Auth checks
    if not github.is_authenticated():
        console.print("[red]GitHub CLI not authenticated. Run: gh auth login[/red]")
        ok = False
    else:
        console.print("  [green]✓[/green] gh authenticated")

    if not ok:
        raise SystemExit("Fix authentication issues above before continuing.")
