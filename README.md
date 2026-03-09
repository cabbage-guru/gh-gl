# gh-gl

Sync repositories between **GitLab** (authoritative) and **GitHub** (disposable private workspace).

The model: GitLab is your source of truth. GitHub is a throwaway sandbox for
AI-agent experimentation. `gh-gl` makes it painless to mirror your repo to a
private GitHub repo, let agents hack on branches there, and then push the good
branches back to GitLab as merge requests.

## Prerequisites

| Tool  | Install |
|-------|---------|
| git   | your OS package manager |
| [gh](https://cli.github.com/) | `brew install gh` / `winget install GitHub.cli` / `apt install gh` |
| [glab](https://gitlab.com/gitlab-org/cli) | `brew install glab` / `winget install GLab.GLab` / `pip install glab` |

Authenticate both CLIs:

```sh
gh auth login
glab auth login --hostname gitlab.example.com   # your custom instance
```

## Install

```sh
pip install -e .
```

## Quick Start

```sh
# 1. cd into your GitLab checkout
cd ~/projects/my-project

# 2. Initialize — creates a PRIVATE GitHub mirror
gh-gl init

# 3. Sync all branches from GitLab → GitHub
gh-gl sync

# 4. (agents do their thing on GitHub branches...)

# 5. Push a branch from GitHub back to GitLab + open MR
gh-gl push-branch feature-from-agent

# 6. See what's where
gh-gl status
```

## Commands

### `gh-gl init`

Sets up the sync relationship. Detects your GitLab remote, creates a **private**
GitHub repo, adds a `github` remote, and saves the config.

```
Options:
  --gitlab-remote TEXT  GitLab remote name (default: origin)
  --github-owner TEXT   GitHub user/org (default: your gh user)
  --github-repo TEXT    Repo name (default: same as GitLab)
  --name TEXT           Project name in config
```

### `gh-gl sync`

Fetches from GitLab and force-pushes all branches + tags to the GitHub mirror.

```
Options:
  -b, --branches TEXT   Comma-separated branch list (default: all)
```

### `gh-gl push-branch [BRANCH]`

Pushes a branch from GitHub to GitLab. If no branch is specified, shows an
interactive picker of GitHub-only branches. Optionally creates a merge request.

```
Options:
  -t, --target TEXT   MR target branch (default: repo default)
  --title TEXT        MR title
  --no-mr             Just push, don't create MR
```

### `gh-gl status`

Fetches both remotes and shows a table of which branches exist where and
whether they're in sync or diverged.

### `gh-gl nuke`

Deletes the GitHub mirror. Safe, because GitLab is authoritative. Cleans up
the remote and config.

### `gh-gl config`

Prints the current configuration.

## Configuration

Stored in `~/.config/gh-gl/config.toml` (respects `XDG_CONFIG_HOME` and
`%APPDATA%` on Windows).

## Design Principles

- **GitLab is authoritative** — `sync` always pushes *from* GitLab *to* GitHub
- **GitHub is disposable** — `nuke` deletes the GitHub repo without worry
- **GitHub repos are PRIVATE** — your confidential code stays confidential
- **Cross-platform** — works on Linux, macOS, Windows (Python 3.10+)
- **Minimal dependencies** — just `click` and `rich` on top of `git`, `gh`, `glab`
