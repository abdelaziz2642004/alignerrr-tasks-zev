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
    """Display basic feedback statistics."""
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

    rprint("\n[dim]Tip: Use 'zev --stats' for detailed statistics with tables.[/dim]")


def show_detailed_stats():
    """Display detailed feedback statistics with Rich tables."""
    console = Console()
    stats = command_history.get_aggregated_stats()

    if stats["total"] == 0:
        rprint("\n[bold]Command Feedback Statistics[/bold]")
        rprint("─" * 30)
        rprint("[dim]No feedback recorded yet.[/dim]")
        rprint("[dim]Feedback is collected automatically when you run zev after using a command.[/dim]")
        return

    # Overview table
    rprint("\n[bold]Overview[/bold]")
    overview_table = Table(show_header=False, box=None, padding=(0, 2))
    overview_table.add_column("Metric", style="dim")
    overview_table.add_column("Value")

    overview_table.add_row("Total Feedback", str(stats["total"]))
    overview_table.add_row("Success Rate", f"[green]{stats['success_rate']:.1f}%[/green]")
    overview_table.add_row("Successful", f"[green]{stats['success']}[/green]")
    overview_table.add_row("Failed", f"[red]{stats['failed']}[/red]")
    overview_table.add_row("Skipped", f"[dim]{stats['skipped']}[/dim]")

    console.print(overview_table)

    # Most used commands table
    if stats["command_stats"]:
        rprint("\n[bold]Most Used Commands[/bold]")
        cmd_table = Table(box=None, padding=(0, 1))
        cmd_table.add_column("Command", style="cyan", max_width=50)
        cmd_table.add_column("Uses", justify="right")
        cmd_table.add_column("Success", justify="right", style="green")
        cmd_table.add_column("Failed", justify="right", style="red")
        cmd_table.add_column("Rate", justify="right")

        for cmd_stat in stats["command_stats"][:10]:  # Top 10
            cmd_display = cmd_stat["command"][:47] + "..." if len(cmd_stat["command"]) > 50 else cmd_stat["command"]
            rate_style = "green" if cmd_stat["success_rate"] >= 70 else "yellow" if cmd_stat["success_rate"] >= 40 else "red"
            rate_display = f"[{rate_style}]{cmd_stat['success_rate']:.0f}%[/{rate_style}]"

            cmd_table.add_row(
                cmd_display,
                str(cmd_stat["total"]),
                str(cmd_stat["success"]),
                str(cmd_stat["failed"]),
                rate_display,
            )

        console.print(cmd_table)

    # Commands with highest failure rates
    failed_commands = [c for c in stats["command_stats"] if c["failed"] > 0]
    failed_commands.sort(key=lambda x: (x["success_rate"], -x["failed"]))  # Lowest success rate first

    if failed_commands:
        rprint("\n[bold]Commands with Highest Failure Rates[/bold]")
        fail_table = Table(box=None, padding=(0, 1))
        fail_table.add_column("Command", style="cyan", max_width=50)
        fail_table.add_column("Failed", justify="right", style="red")
        fail_table.add_column("Total", justify="right")
        fail_table.add_column("Failure Rate", justify="right")

        for cmd_stat in failed_commands[:5]:  # Top 5 failing
            cmd_display = cmd_stat["command"][:47] + "..." if len(cmd_stat["command"]) > 50 else cmd_stat["command"]
            failure_rate = 100 - cmd_stat["success_rate"]
            fail_table.add_row(
                cmd_display,
                str(cmd_stat["failed"]),
                str(cmd_stat["total"]),
                f"[red]{failure_rate:.0f}%[/red]",
            )

        console.print(fail_table)

    # Recent failures with notes
    if stats["recent_failures"]:
        rprint("\n[bold]Recent Failures[/bold]")
        for failure in stats["recent_failures"]:
            cmd_display = failure["command"][:60] + "..." if len(failure["command"]) > 60 else failure["command"]
            rprint(f"  [red]✗[/red] {cmd_display}")
            if failure["notes"]:
                rprint(f"    [dim]Note: {failure['notes']}[/dim]")


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
