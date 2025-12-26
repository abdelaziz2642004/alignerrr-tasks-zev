import sys
from pathlib import Path

import dotenv
from rich import print as rprint
from rich.console import Console

from zev.command_history import CommandHistory
from zev.command_selector import prompt_for_feedback, show_options
from zev.config import config
from zev.config.setup import run_setup
from zev.constants import CONFIG_FILE_NAME
from zev.llms.llm import get_inference_provider
from zev.utils import get_env_context, get_input_string, show_help

command_history = CommandHistory()


def setup():
    run_setup()


def check_pending_feedback() -> bool:
    """Check for and handle pending feedback from previous command. Returns True if feedback was collected."""
    pending = command_history.get_pending_feedback()
    if pending:
        prompt_for_feedback(
            pending.command,
            pending.query,
            command_history._feedback_callback
        )
        command_history.clear_pending_feedback()
        return True
    return False


def get_options(words: str):
    context = get_env_context()
    console = Console()
    rprint(f"")
    with console.status(
        f"[bold blue]Thinking... [grey39](running query using {config.llm_provider} backend)", spinner="dots"
    ):
        inference_provider = get_inference_provider()
        response = inference_provider.get_options(prompt=words, context=context)
        command_history.save_options(words, response)

    if response is None:
        return

    if not response.is_valid:
        print(response.explanation_if_not_valid)
        return

    if not response.commands:
        print("No commands available")
        return

    show_options(response.commands, query=words, save_pending_callback=command_history.save_pending_feedback)


def run_no_prompt():
    input = get_input_string("input", "Describe what you want to do:", required=False, help_text="(-h for help)")
    if handle_special_case(input):
        return
    get_options(input)


def handle_special_case(args):
    if not args:
        return False

    if isinstance(args, str):
        args = args.split()

    if len(args) > 1:
        return False

    command = args[0].lower()

    if command == "--setup" or command == "-s":
        setup()
        return True

    if command == "--version" or command == "-v":
        print("zev version: 0.8.1")
        return True

    if command == "--recent" or command == "-r":
        command_history.show_history()
        return True

    if command == "--feedback" or command == "-f":
        show_feedback_stats()
        return True

    if command == "--help" or command == "-h":
        show_help()
        return True

    return False


def show_feedback_stats():
    """Display feedback statistics."""
    stats = command_history.get_feedback_stats()

    rprint("\n[bold]Command Feedback Statistics[/bold]")
    rprint("─" * 30)

    if stats["total"] == 0:
        rprint("[dim]No feedback recorded yet.[/dim]")
        rprint("[dim]Feedback is collected automatically when you run zev after using a command.[/dim]")
        return

    success_pct = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
    failed_pct = (stats["failed"] / stats["total"]) * 100 if stats["total"] > 0 else 0

    rprint(f"Total feedback entries: {stats['total']}")
    rprint(f"[green]✓ Successful:[/green] {stats['success']} ({success_pct:.1f}%)")
    rprint(f"[red]✗ Failed:[/red] {stats['failed']} ({failed_pct:.1f}%)")
    rprint(f"[dim]○ Skipped:[/dim] {stats['skipped']}")

    # Show recent feedback entries
    feedback_entries = command_history.get_feedback()
    if feedback_entries:
        rprint("\n[bold]Recent Feedback:[/bold]")
        for entry in reversed(feedback_entries[-5:]):
            status_icon = "[green]✓[/green]" if entry.feedback.value == "success" else "[red]✗[/red]" if entry.feedback.value == "failed" else "[dim]○[/dim]"
            cmd_display = entry.command[:50] + ('...' if len(entry.command) > 50 else '')
            rprint(f"  {status_icon} {cmd_display}")
            if entry.notes:
                rprint(f"      [dim]Note: {entry.notes[:60]}{'...' if len(entry.notes) > 60 else ''}[/dim]")


def app():
    # check if .zevrc exists or if setting up again
    config_path = Path.home() / CONFIG_FILE_NAME
    args = [arg.strip() for arg in sys.argv[1:]]

    if not config_path.exists():
        run_setup()
        print("Setup complete...\n")
        if len(args) == 1 and args[0] == "--setup":
            return

    if handle_special_case(args):
        return

    dotenv.load_dotenv(config_path, override=True)

    # Check for pending feedback from previous command before proceeding
    check_pending_feedback()

    if not args:
        run_no_prompt()
        return

    # Strip any trailing question marks from the input
    query = " ".join(args).rstrip("?")
    get_options(query)


if __name__ == "__main__":
    app()
