from subprocess import run as run_command
from typing import Optional, Callable

import pyperclip
import questionary
from rich import print as rprint

from zev.llms.types import Command, CommandFeedback


def show_options(commands: list[Command], on_feedback: Optional[Callable[[Command, CommandFeedback], None]] = None):
    options = assemble_options(commands)
    selected = display_options(options)
    handle_selected_option(selected, on_feedback)


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


def handle_selected_option(selected, on_feedback: Optional[Callable[[Command, CommandFeedback], None]] = None):
    if selected and selected != "Cancel":
        print("")
        if selected.dangerous_explanation:
            rprint(f"[red]⚠️ Warning: {selected.dangerous_explanation}[/red]\n")
        try:
            pyperclip.copy(selected.command)
            rprint("[green]✓[/green] Copied to clipboard")
        except pyperclip.PyperclipException as e:
            rprint(
                "[red]Could not copy to clipboard (see https://github.com/dtnewman/zev?tab=readme-ov-file#-dependencies)[/red]\n"
            )
            rprint("[cyan]Here is your command:[/cyan]")
            print(selected.command)
            if questionary.confirm("Would you like to run it?").ask():
                print("Running command:", selected.command)
                run_command(selected.command, shell=True)

        # Ask for optional feedback
        feedback = prompt_for_feedback()
        if feedback and on_feedback:
            on_feedback(selected, feedback)


def prompt_for_feedback() -> Optional[CommandFeedback]:
    """Prompt user to optionally report whether the command worked."""
    style = questionary.Style(
        [
            ("answer", "fg:#61afef"),
            ("question", "bold"),
            ("instruction", "fg:#98c379"),
        ]
    )

    choices = [
        questionary.Choice("Skip feedback", value=None),
        questionary.Choice("✓ Command worked", value=CommandFeedback.SUCCESS),
        questionary.Choice("✗ Command failed", value=CommandFeedback.FAILED),
    ]

    print("")
    result = questionary.select(
        "How did the command work? (optional):",
        choices=choices,
        style=style,
        instruction="(run the command first, then report back)"
    ).ask()

    if result == CommandFeedback.SUCCESS:
        rprint("[green]Thanks! Feedback recorded.[/green]")
    elif result == CommandFeedback.FAILED:
        rprint("[yellow]Thanks! Feedback recorded.[/yellow]")

    return result
