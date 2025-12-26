import sys
from pathlib import Path

import dotenv
from rich import print as rprint
from rich.console import Console
from rich.table import Table

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
    # Check for pending feedback before processing new query
    check_pending_feedback()

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

    if command == "--stats":
        show_detailed_stats()
        return True

    if command == "--help" or command == "-h":
        show_help()
        return True

    return False


def show_feedback_stats():
    """Display brief feedback statistics."""
    stats = command_history.get_feedback_stats()

    rprint("\n[bold]Command Feedback Summary[/bold]")
    rprint("─" * 30)

    if stats["total"] == 0:
        rprint("[dim]No feedback recorded yet.[/dim]")
        rprint("[dim]Feedback is collected automatically when you run zev after using a command.[/dim]")
        rprint("\n[dim]Use 'zev --stats' for detailed statistics.[/dim]")
        return

    success_pct = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
    failed_pct = (stats["failed"] / stats["total"]) * 100 if stats["total"] > 0 else 0

    rprint(f"Total feedback entries: {stats['total']}")
    rprint(f"[green]✓ Successful:[/green] {stats['success']} ({success_pct:.1f}%)")
    rprint(f"[red]✗ Failed:[/red] {stats['failed']} ({failed_pct:.1f}%)")
    rprint(f"[dim]○ Skipped:[/dim] {stats['skipped']}")
    rprint("\n[dim]Use 'zev --stats' for detailed statistics.[/dim]")


def show_detailed_stats():
    """Display detailed feedback statistics with Rich tables."""
    console = Console()
    stats = command_history.get_aggregated_stats()

    if stats["total_feedback"] == 0:
        rprint("\n[bold]Command Feedback Statistics[/bold]")
        rprint("─" * 30)
        rprint("[dim]No feedback recorded yet.[/dim]")
        rprint("[dim]Feedback is collected automatically when you run zev after using a command.[/dim]")
        return

    # Overall Summary Table
    rprint("\n[bold]Overall Statistics[/bold]")
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Total Feedback", str(stats["total_feedback"]))
    summary_table.add_row("Success Rate", f"[green]{stats['success_rate']:.1f}%[/green]")
    summary_table.add_row("Failure Rate", f"[red]{stats['failure_rate']:.1f}%[/red]")
    summary_table.add_row(
        "Breakdown",
        f"[green]✓ {stats['success_count']}[/green] / [red]✗ {stats['failed_count']}[/red] / [dim]○ {stats['skipped_count']}[/dim]"
    )
    console.print(summary_table)

    # Most Used Commands Table
    if stats.get("most_used"):
        rprint("\n[bold]Most Used Commands[/bold]")
        used_table = Table(box=None, padding=(0, 1))
        used_table.add_column("Command", style="white", max_width=50, overflow="ellipsis")
        used_table.add_column("Uses", style="cyan", justify="right")
        used_table.add_column("Success", style="green", justify="right")
        used_table.add_column("Failed", style="red", justify="right")
        used_table.add_column("Rate", justify="right")

        for cmd_stat in stats["most_used"]:
            cmd_display = cmd_stat["command"][:50]
            if len(cmd_stat["command"]) > 50:
                cmd_display += "..."
            rate_color = "green" if cmd_stat["success_rate"] >= 70 else "yellow" if cmd_stat["success_rate"] >= 40 else "red"
            used_table.add_row(
                cmd_display,
                str(cmd_stat["total"]),
                str(cmd_stat["success"]),
                str(cmd_stat["failed"]),
                f"[{rate_color}]{cmd_stat['success_rate']:.0f}%[/{rate_color}]"
            )
        console.print(used_table)

    # Highest Failure Commands Table
    if stats.get("highest_failures"):
        rprint("\n[bold]Commands with Most Failures[/bold]")
        fail_table = Table(box=None, padding=(0, 1))
        fail_table.add_column("Command", style="white", max_width=50, overflow="ellipsis")
        fail_table.add_column("Failures", style="red", justify="right")
        fail_table.add_column("Total", style="dim", justify="right")
        fail_table.add_column("Fail Rate", style="red", justify="right")

        for cmd_stat in stats["highest_failures"]:
            cmd_display = cmd_stat["command"][:50]
            if len(cmd_stat["command"]) > 50:
                cmd_display += "..."
            fail_rate = (cmd_stat["failed"] / cmd_stat["total"]) * 100 if cmd_stat["total"] > 0 else 0
            fail_table.add_row(
                cmd_display,
                str(cmd_stat["failed"]),
                str(cmd_stat["total"]),
                f"{fail_rate:.0f}%"
            )
        console.print(fail_table)

    # Recent Failures with Notes
    if stats.get("recent_failures"):
        rprint("\n[bold]Recent Failures[/bold]")
        for failure in stats["recent_failures"]:
            cmd_display = failure["command"][:60]
            if len(failure["command"]) > 60:
                cmd_display += "..."
            rprint(f"  [red]✗[/red] {cmd_display}")
            if failure.get("notes"):
                notes_display = failure["notes"][:80]
                if len(failure["notes"]) > 80:
                    notes_display += "..."
                rprint(f"    [dim]Note: {notes_display}[/dim]")


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

    if not args:
        run_no_prompt()
        return

    # Strip any trailing question marks from the input
    query = " ".join(args).rstrip("?")
    get_options(query)


if __name__ == "__main__":
    app()
