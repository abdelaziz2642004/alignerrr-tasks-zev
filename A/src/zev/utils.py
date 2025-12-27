import os
import platform
import subprocess
import time

import questionary

# Cache for get_env_context()
_env_context_cache = {"value": None, "timestamp": 0, "cwd": None}
_ENV_CONTEXT_CACHE_TTL = 2  # seconds

CLI_STYLE = questionary.Style(
    [
        ("qmark", "#98c379"),
        ("question", "#98c379"),
        ("instruction", "italic #646464"),
    ]
)


def get_input_string(
    field_name: str,
    prompt_text: str,
    default: str = "",
    required: bool = False,
    help_text: str = "",
) -> str:
    """Ask for a single line of input in the terminal, with colour + hint."""
    base = f"{prompt_text} (default: {default})" if default else prompt_text

    while True:
        value = questionary.text(
            message=base,
            default=default,
            instruction=help_text or None,
            style=CLI_STYLE,
            validate=lambda t: bool(t) if required else True,
        ).ask()

        if value is None:  # user pressed Ctrl-C / Ctrl-D
            raise KeyboardInterrupt
        if value == "" and default:  # user just hit ↵
            return default
        if value or not required:
            return value

        # Required but empty ─ repeat
        print(f"{field_name} is required, please try again.")


def _get_git_info() -> dict:
    """Get git repository information if in a git repo.

    Optimized to use a single git command for all info.
    """
    git_info = {"is_git_repo": False, "branch": None, "status_summary": None}

    try:
        # Single command to get branch and status info
        # --porcelain=v1 --branch gives us branch info in first line(s) + status
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--branch"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return git_info

        git_info["is_git_repo"] = True
        lines = result.stdout.split("\n")

        # Parse branch info from first line (format: "## branch...tracking")
        if lines and lines[0].startswith("## "):
            branch_line = lines[0][3:]  # Remove "## "
            # Handle detached HEAD: "## HEAD (no branch)" or "## <commit>..."
            if branch_line.startswith("HEAD (no branch)"):
                # Get short commit hash with separate command (only in detached state)
                commit_result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if commit_result.returncode == 0:
                    git_info["branch"] = f"detached at {commit_result.stdout.strip()}"
            else:
                # Extract branch name (before "..." if tracking info present)
                branch = branch_line.split("...")[0]
                git_info["branch"] = branch

        # Parse status (skip branch line)
        status_lines = [l for l in lines[1:] if l]
        if not status_lines:
            git_info["status_summary"] = "clean"
        else:
            # Git porcelain format: XY where X=staged, Y=unstaged
            # X can be: M (modified), A (added), D (deleted), R (renamed), C (copied), U (unmerged)
            # Y can be: M (modified), D (deleted), U (unmerged)
            # Special cases: ?? (untracked), !! (ignored), UU/AA/DD/etc (conflicts)
            staged = 0
            unstaged = 0
            untracked = 0
            conflicts = 0

            for line in status_lines:
                if len(line) < 2:
                    continue
                x, y = line[0], line[1]

                # Untracked files
                if x == "?" and y == "?":
                    untracked += 1
                # Ignored files (skip)
                elif x == "!" and y == "!":
                    continue
                # Unmerged/conflict states
                elif x == "U" or y == "U" or (x == y and x in "AD"):
                    conflicts += 1
                else:
                    # Staged changes (index column)
                    if x in "MADRC":
                        staged += 1
                    # Unstaged changes (worktree column)
                    if y in "MD":
                        unstaged += 1

            parts = []
            if staged:
                parts.append(f"{staged} staged")
            if unstaged:
                parts.append(f"{unstaged} modified")
            if untracked:
                parts.append(f"{untracked} untracked")
            if conflicts:
                parts.append(f"{conflicts} conflicts")
            git_info["status_summary"] = ", ".join(parts) if parts else "clean"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # git not available or timed out
        pass

    return git_info


def get_env_context() -> str:
    """Gather environment context including OS, shell, directory, and git info.

    Results are cached for 2 seconds to avoid redundant git commands when
    called multiple times in quick succession.
    """
    global _env_context_cache

    current_time = time.time()
    cwd = os.getcwd()

    # Return cached result if still valid and in same directory
    if (
        _env_context_cache["value"] is not None
        and _env_context_cache["cwd"] == cwd
        and (current_time - _env_context_cache["timestamp"]) < _ENV_CONTEXT_CACHE_TTL
    ):
        return _env_context_cache["value"]

    context_parts = []

    # OS information
    os_name = platform.platform(aliased=True)
    context_parts.append(f"OS: {os_name}")

    # Shell information
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC")
    if shell:
        context_parts.append(f"SHELL: {shell}")

    # Current directory
    context_parts.append(f"CWD: {cwd}")

    # Git information
    git_info = _get_git_info()
    if git_info["is_git_repo"]:
        context_parts.append("GIT_REPO: yes")
        if git_info["branch"]:
            context_parts.append(f"GIT_BRANCH: {git_info['branch']}")
        if git_info["status_summary"]:
            context_parts.append(f"GIT_STATUS: {git_info['status_summary']}")
    else:
        context_parts.append("GIT_REPO: no")

    result = "\n".join(context_parts)

    # Update cache
    _env_context_cache["value"] = result
    _env_context_cache["timestamp"] = current_time
    _env_context_cache["cwd"] = cwd

    return result


def show_help():
    print("""
Zev is a simple CLI tool to help you remember terminal commands.

Usage:
zev "<query>"               Describe what you want to do
zev --help, -h            Show this help message
zev --recent, -r          Show recently run commands and results
zev --setup, -s           Run setup again
zev --version, -v         Show version information
""")
