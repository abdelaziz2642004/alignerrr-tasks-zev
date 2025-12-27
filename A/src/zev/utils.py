import os
import platform
import subprocess

import questionary

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
    """Get git repository information if in a git repo."""
    git_info = {"is_git_repo": False, "branch": None, "status_summary": None}

    try:
        # Check if we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return git_info

        git_info["is_git_repo"] = True

        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch:
                git_info["branch"] = branch
            else:
                # Detached HEAD state - get short commit hash
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    git_info["branch"] = f"detached at {result.stdout.strip()}"

        # Get status summary
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            status_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            if not status_lines or status_lines == [""]:
                git_info["status_summary"] = "clean"
            else:
                staged = sum(1 for line in status_lines if line and line[0] in "MADRCU")
                unstaged = sum(1 for line in status_lines if line and len(line) > 1 and line[1] in "MADRCU")
                untracked = sum(1 for line in status_lines if line and line.startswith("??"))

                parts = []
                if staged:
                    parts.append(f"{staged} staged")
                if unstaged:
                    parts.append(f"{unstaged} modified")
                if untracked:
                    parts.append(f"{untracked} untracked")
                git_info["status_summary"] = ", ".join(parts) if parts else "clean"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # git not available or timed out
        pass

    return git_info


def get_env_context() -> str:
    """Gather environment context including OS, shell, directory, and git info."""
    context_parts = []

    # OS information
    os_name = platform.platform(aliased=True)
    context_parts.append(f"OS: {os_name}")

    # Shell information
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC")
    if shell:
        context_parts.append(f"SHELL: {shell}")

    # Current directory
    cwd = os.getcwd()
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

    return "\n".join(context_parts)


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
