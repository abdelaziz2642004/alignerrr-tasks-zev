from subprocess import run as run_command
from typing import Callable, Optional

import pyperclip
import questionary
from rich import print as rprint

from zev.llms.types import Command


def show_options(commands: list[Command], query: str = "", feedback_callback: Optional[Callable] = None):
    options = assemble_options(commands)
    selected = display_options(options)
    handle_selected_option(selected, query, feedback_callback)


def assemble_options(commands: list[Command]):
    options = [questionary.Choice(cmd.command, description=cmd.short_explanation, value=cmd) for cmd in commands]
    options.append(questionary.Choice("Cancel"))
    options.append(questionary.Separator())
    return options


def display_options(options: list[questionary.Choice]):
    selected = questionary.select(
        "Select command:",
        choices=options,
        use_shortcuts=True,
        style=questionary.Style(
            [
                ("answer", "fg:#61afef"),
                ("question", "bold"),
                ("instruction", "fg:#98c379"),
            ]
        ),
    ).ask()
    return selected


def handle_selected_option(selected, query: str = "", feedback_callback: Optional[Callable] = None):
    if selected and selected != "Cancel":
        print("")
        if selected.dangerous_explanation:
            rprint(f"[red]⚠️ Warning: {selected.dangerous_explanation}[/red]\n")
        try:
            pyperclip.copy(selected.command)
            rprint("[green]✓[/green] Copied to clipboard")

            # Store the selected command for feedback on next run
            if feedback_callback:
                _store_pending_feedback(selected.command, query)
        except pyperclip.PyperclipException as e:
            rprint(
                "[red]Could not copy to clipboard (see https://github.com/dtnewman/zev?tab=readme-ov-file#-dependencies)[/red]\n"
            )
            rprint("[cyan]Here is your command:[/cyan]")
            print(selected.command)
            if questionary.confirm("Would you like to run it?").ask():
                print("Running command:", selected.command)
                run_command(selected.command, shell=True)
                # Prompt for feedback after running
                if feedback_callback:
                    prompt_for_feedback(selected.command, query, feedback_callback)


def _store_pending_feedback(command: str, query: str) -> None:
    """Store pending feedback info for later retrieval on next zev run."""
    from pathlib import Path
    import json

    pending_file = Path.home() / ".zev_pending_feedback"
    pending_data = {
        "command": command,
        "query": query,
    }
    with open(pending_file, "w") as f:
        json.dump(pending_data, f)


def prompt_for_feedback(command: str, query: str, feedback_callback: Callable) -> None:
    """Prompt user for feedback on whether the command worked."""
    style = questionary.Style([
        ("answer", "fg:#61afef"),
        ("question", "bold"),
        ("instruction", "fg:#98c379"),
    ])

    feedback_choice = questionary.select(
        "Did the command work?",
        choices=[
            questionary.Choice("Yes, it worked!", value="success"),
            questionary.Choice("No, it failed", value="failed"),
            questionary.Choice("Skip feedback", value="skipped"),
        ],
        use_shortcuts=True,
        style=style,
    ).ask()

    if feedback_choice and feedback_callback:
        failure_notes = None

        # If the command failed, ask for optional notes about what went wrong
        if feedback_choice == "failed":
            failure_notes = questionary.text(
                "What went wrong? (optional, press Enter to skip)",
                style=style,
            ).ask()
            # Treat empty string as None
            if failure_notes == "":
                failure_notes = None

        feedback_callback(command, query, feedback_choice, failure_notes)

        if feedback_choice == "success":
            rprint("[green]✓[/green] Thanks for the feedback!")
        elif feedback_choice == "failed":
            rprint("[yellow]![/yellow] Feedback recorded. Sorry it didn't work!")
