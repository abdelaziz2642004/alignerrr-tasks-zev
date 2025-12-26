from subprocess import run as run_command

import pyperclip
import questionary
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from zev.llms.types import Command, Workflow


def show_options(commands: list[Command], workflows: list[Workflow] = None):
    workflows = workflows or []
    options = assemble_options(commands, workflows)
    selected = display_options(options)
    handle_selected_option(selected)


def assemble_options(commands: list[Command], workflows: list[Workflow] = None):
    workflows = workflows or []
    options = []

    # Add single commands
    for cmd in commands:
        options.append(questionary.Choice(cmd.command, description=cmd.short_explanation, value=cmd))

    # Add workflows with a visual separator if both exist
    if commands and workflows:
        options.append(questionary.Separator("─── Workflows ───"))

    for workflow in workflows:
        step_count = len(workflow.steps)
        display_name = f"[Workflow] {workflow.name} ({step_count} steps)"
        options.append(questionary.Choice(display_name, description=workflow.description, value=workflow))

    options.append(questionary.Separator())
    options.append(questionary.Choice("Cancel"))
    return options


def display_options(options: list[questionary.Choice]):
    selected = questionary.select(
        "Select command or workflow:",
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


def handle_selected_option(selected):
    if selected and selected != "Cancel":
        print("")
        if isinstance(selected, Workflow):
            handle_workflow(selected)
        else:
            handle_single_command(selected)


def handle_single_command(selected: Command):
    if selected.dangerous_explanation:
        rprint(f"[red]Warning: {selected.dangerous_explanation}[/red]\n")
    try:
        pyperclip.copy(selected.command)
        rprint("[green]✓[/green] Copied to clipboard")
    except pyperclip.PyperclipException:
        rprint(
            "[red]Could not copy to clipboard (see https://github.com/dtnewman/zev?tab=readme-ov-file#-dependencies)[/red]\n"
        )
        rprint("[cyan]Here is your command:[/cyan]")
        print(selected.command)
        if questionary.confirm("Would you like to run it?").ask():
            print("Running command:", selected.command)
            run_command(selected.command, shell=True)


def handle_workflow(workflow: Workflow):
    console = Console()

    # Display workflow overview
    display_workflow_overview(console, workflow)

    # Show dangerous warning if applicable
    if workflow.is_dangerous:
        rprint(f"\n[red]Warning: This workflow contains dangerous operations![/red]")
        for step in workflow.steps:
            if step.is_dangerous and step.dangerous_explanation:
                rprint(f"[red]  Step {step.step_number}: {step.dangerous_explanation}[/red]")

    # Ask user what they want to do
    action = questionary.select(
        "\nWhat would you like to do?",
        choices=[
            questionary.Choice("Run all steps sequentially", value="run_all"),
            questionary.Choice("Copy all commands to clipboard", value="copy_all"),
            questionary.Choice("Step through interactively", value="interactive"),
            questionary.Choice("Cancel", value="cancel"),
        ],
        style=questionary.Style(
            [
                ("answer", "fg:#61afef"),
                ("question", "bold"),
                ("instruction", "fg:#98c379"),
            ]
        ),
    ).ask()

    if action == "run_all":
        run_workflow_all(workflow)
    elif action == "copy_all":
        copy_workflow_commands(workflow)
    elif action == "interactive":
        run_workflow_interactive(workflow)


def display_workflow_overview(console: Console, workflow: Workflow):
    table = Table(title=f"Workflow: {workflow.name}", show_header=True, header_style="bold cyan")
    table.add_column("Step", style="dim", width=6)
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_column("Depends", width=8)

    for step in workflow.steps:
        danger_marker = "[red]*[/red]" if step.is_dangerous else ""
        depends = "Yes" if step.depends_on_previous else "No"
        table.add_row(
            f"{step.step_number}{danger_marker}",
            step.command,
            step.description,
            depends
        )

    console.print(table)
    console.print(f"\n[dim]{workflow.description}[/dim]")


def run_workflow_all(workflow: Workflow):
    rprint("\n[bold cyan]Running workflow...[/bold cyan]\n")

    for step in workflow.steps:
        rprint(f"[bold]Step {step.step_number}:[/bold] {step.description}")
        rprint(f"[dim]$ {step.command}[/dim]")

        if step.is_dangerous and step.dangerous_explanation:
            rprint(f"[red]Warning: {step.dangerous_explanation}[/red]")
            if not questionary.confirm("Continue with this dangerous step?").ask():
                rprint("[yellow]Workflow aborted by user.[/yellow]")
                return

        result = run_command(step.command, shell=True)

        if result.returncode != 0:
            rprint(f"[red]Step {step.step_number} failed with exit code {result.returncode}[/red]")
            if step.depends_on_previous or step.step_number < len(workflow.steps):
                next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
                if next_step and next_step.depends_on_previous:
                    rprint("[yellow]Stopping workflow because next step depends on this one.[/yellow]")
                    return
                elif not questionary.confirm("Continue with remaining steps?").ask():
                    rprint("[yellow]Workflow aborted by user.[/yellow]")
                    return
        else:
            rprint(f"[green]✓[/green] Step {step.step_number} completed\n")

    rprint("[bold green]Workflow completed successfully![/bold green]")


def copy_workflow_commands(workflow: Workflow):
    # Join all commands with newlines for easy pasting
    all_commands = "\n".join(step.command for step in workflow.steps)
    try:
        pyperclip.copy(all_commands)
        rprint(f"[green]✓[/green] Copied {len(workflow.steps)} commands to clipboard")
        rprint("\n[dim]Commands copied:[/dim]")
        for step in workflow.steps:
            rprint(f"[dim]  {step.step_number}. {step.command}[/dim]")
    except pyperclip.PyperclipException:
        rprint(
            "[red]Could not copy to clipboard (see https://github.com/dtnewman/zev?tab=readme-ov-file#-dependencies)[/red]\n"
        )
        rprint("[cyan]Here are your commands:[/cyan]")
        for step in workflow.steps:
            print(f"{step.step_number}. {step.command}")


def run_workflow_interactive(workflow: Workflow):
    rprint("\n[bold cyan]Interactive workflow mode[/bold cyan]")
    rprint("[dim]You will be prompted before each step.[/dim]\n")

    for step in workflow.steps:
        rprint(f"\n[bold]Step {step.step_number}/{len(workflow.steps)}:[/bold] {step.description}")
        rprint(f"[cyan]$ {step.command}[/cyan]")

        if step.is_dangerous and step.dangerous_explanation:
            rprint(f"[red]Warning: {step.dangerous_explanation}[/red]")

        action = questionary.select(
            "Action:",
            choices=[
                questionary.Choice("Run this step", value="run"),
                questionary.Choice("Skip this step", value="skip"),
                questionary.Choice("Copy to clipboard", value="copy"),
                questionary.Choice("Abort workflow", value="abort"),
            ],
            style=questionary.Style(
                [
                    ("answer", "fg:#61afef"),
                    ("question", "bold"),
                    ("instruction", "fg:#98c379"),
                ]
            ),
        ).ask()

        if action == "abort":
            rprint("[yellow]Workflow aborted by user.[/yellow]")
            return
        elif action == "skip":
            rprint(f"[yellow]Skipped step {step.step_number}[/yellow]")
            # Check if next step depends on this one
            next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
            if next_step and next_step.depends_on_previous:
                rprint("[yellow]Warning: Next step depends on this one![/yellow]")
            continue
        elif action == "copy":
            try:
                pyperclip.copy(step.command)
                rprint(f"[green]✓[/green] Copied to clipboard")
            except pyperclip.PyperclipException:
                rprint(f"[red]Could not copy to clipboard[/red]")
            continue
        elif action == "run":
            result = run_command(step.command, shell=True)
            if result.returncode != 0:
                rprint(f"[red]Step failed with exit code {result.returncode}[/red]")
                next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
                if next_step and next_step.depends_on_previous:
                    rprint("[yellow]Warning: Next step depends on this one![/yellow]")
            else:
                rprint(f"[green]✓[/green] Step {step.step_number} completed")

    rprint("\n[bold green]Interactive workflow completed![/bold green]")
