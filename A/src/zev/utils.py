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


def _run_git_command(args: list[str]) -> str | None:
    """Run a git command and return output, or None if it fails."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _get_git_context() -> str | None:
    """Get git repository context if in a git repo."""
    # Check if we're in a git repo
    if _run_git_command(["rev-parse", "--is-inside-work-tree"]) != "true":
        return None

    context_parts = ["Git repo: Yes"]

    # Get current branch
    branch = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch:
        context_parts.append(f"Branch: {branch}")

    # Get status summary
    status_output = _run_git_command(["status", "--porcelain"])
    if status_output is not None:
        if status_output == "":
            context_parts.append("Status: Clean")
        else:
            # Count different types of changes
            lines = status_output.split("\n")
            staged = sum(1 for line in lines if line and line[0] in "MADRC")
            unstaged = sum(1 for line in lines if line and len(line) > 1 and line[1] in "MD")
            untracked = sum(1 for line in lines if line.startswith("??"))

            status_parts = []
            if staged:
                status_parts.append(f"{staged} staged")
            if unstaged:
                status_parts.append(f"{unstaged} modified")
            if untracked:
                status_parts.append(f"{untracked} untracked")

            if status_parts:
                context_parts.append(f"Status: {', '.join(status_parts)}")

    return "\n".join(context_parts)


def _get_directory_context() -> str:
    """Get current directory and its contents summary."""
    cwd = os.getcwd()
    context_parts = [f"Current directory: {cwd}"]

    try:
        entries = os.listdir(cwd)
        files = [e for e in entries if os.path.isfile(os.path.join(cwd, e))]
        dirs = [e for e in entries if os.path.isdir(os.path.join(cwd, e))]

        # Show counts
        context_parts.append(f"Contents: {len(files)} files, {len(dirs)} directories")

        # List some key files/dirs (limit to avoid overwhelming context)
        visible_entries = [e for e in entries if not e.startswith(".")][:15]
        if visible_entries:
            context_parts.append(f"Notable items: {', '.join(visible_entries)}")
    except OSError:
        pass  # Can't read directory, skip contents

    return "\n".join(context_parts)


def get_env_context() -> str:
    """Gather environment context including OS, shell, directory, and git info."""
    os_name = platform.platform(aliased=True)
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC")

    context_parts = [f"OS: {os_name}"]
    if shell:
        context_parts.append(f"SHELL: {shell}")

    # Add directory context
    context_parts.append(_get_directory_context())

    # Add git context if in a repo
    git_context = _get_git_context()
    if git_context:
        context_parts.append(git_context)
    else:
        context_parts.append("Git repo: No")

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
