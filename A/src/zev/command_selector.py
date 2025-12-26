import os
from subprocess import run as run_command
from typing import Optional

import pyperclip
import questionary
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from zev.llms.types import Command, Workflow
from zev.workflow_state import (
    StepStatus,
    WorkflowExecutionState,
    workflow_state_manager,
)


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


def run_workflow_all(
    workflow: Workflow,
    execution_state: Optional[WorkflowExecutionState] = None,
    start_from_step: int = 1
):
    rprint("\n[bold cyan]Running workflow...[/bold cyan]\n")

    # Create execution state if not resuming
    if execution_state is None:
        execution_state = workflow_state_manager.create_execution_state(
            workflow, os.getcwd()
        )
        rprint(f"[dim]Workflow ID: {execution_state.id} (use 'zev --resume' if interrupted)[/dim]\n")

    for step in workflow.steps:
        # Skip already completed steps when resuming
        if step.step_number < start_from_step:
            continue

        rprint(f"[bold]Step {step.step_number}:[/bold] {step.description}")
        rprint(f"[dim]$ {step.command}[/dim]")

        if step.is_dangerous and step.dangerous_explanation:
            rprint(f"[red]Warning: {step.dangerous_explanation}[/red]")
            if not questionary.confirm("Continue with this dangerous step?").ask():
                rprint("[yellow]Workflow paused by user.[/yellow]")
                rprint(f"[dim]Resume with: zev --resume[/dim]")
                return

        result = run_command(step.command, shell=True)

        if result.returncode != 0:
            workflow_state_manager.update_step_status(
                execution_state, step.step_number, StepStatus.FAILED, result.returncode
            )
            rprint(f"[red]Step {step.step_number} failed with exit code {result.returncode}[/red]")
            next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
            if next_step and next_step.depends_on_previous:
                rprint("[yellow]Stopping workflow because next step depends on this one.[/yellow]")
                rprint(f"[dim]Fix the issue and resume with: zev --resume[/dim]")
                return
            elif not questionary.confirm("Continue with remaining steps?").ask():
                rprint("[yellow]Workflow paused by user.[/yellow]")
                rprint(f"[dim]Resume with: zev --resume[/dim]")
                return
        else:
            workflow_state_manager.update_step_status(
                execution_state, step.step_number, StepStatus.COMPLETED, 0
            )
            rprint(f"[green]✓[/green] Step {step.step_number} completed\n")

    workflow_state_manager.mark_complete(execution_state)
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


def run_workflow_interactive(
    workflow: Workflow,
    execution_state: Optional[WorkflowExecutionState] = None,
    start_from_step: int = 1
):
    rprint("\n[bold cyan]Interactive workflow mode[/bold cyan]")
    rprint("[dim]You will be prompted before each step.[/dim]\n")

    # Create execution state if not resuming
    if execution_state is None:
        execution_state = workflow_state_manager.create_execution_state(
            workflow, os.getcwd()
        )
        rprint(f"[dim]Workflow ID: {execution_state.id} (use 'zev --resume' if interrupted)[/dim]")

    for step in workflow.steps:
        # Skip already completed steps when resuming
        if step.step_number < start_from_step:
            continue

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
                questionary.Choice("Pause workflow", value="pause"),
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
            workflow_state_manager.mark_complete(execution_state)
            rprint("[yellow]Workflow aborted by user.[/yellow]")
            return
        elif action == "pause":
            rprint("[yellow]Workflow paused.[/yellow]")
            rprint(f"[dim]Resume with: zev --resume[/dim]")
            return
        elif action == "skip":
            workflow_state_manager.update_step_status(
                execution_state, step.step_number, StepStatus.SKIPPED
            )
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
            # Don't continue - let them choose again for this step
            continue
        elif action == "run":
            result = run_command(step.command, shell=True)
            if result.returncode != 0:
                workflow_state_manager.update_step_status(
                    execution_state, step.step_number, StepStatus.FAILED, result.returncode
                )
                rprint(f"[red]Step failed with exit code {result.returncode}[/red]")
                next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
                if next_step and next_step.depends_on_previous:
                    rprint("[yellow]Warning: Next step depends on this one![/yellow]")
            else:
                workflow_state_manager.update_step_status(
                    execution_state, step.step_number, StepStatus.COMPLETED, 0
                )
                rprint(f"[green]✓[/green] Step {step.step_number} completed")

    workflow_state_manager.mark_complete(execution_state)
    rprint("\n[bold green]Interactive workflow completed![/bold green]")


def show_incomplete_workflows():
    """Display and allow resuming incomplete workflows."""
    incomplete = workflow_state_manager.get_incomplete_workflows()

    if not incomplete:
        rprint("[dim]No incomplete workflows found.[/dim]")
        return

    console = Console()
    rprint(f"\n[bold]Found {len(incomplete)} incomplete workflow(s):[/bold]\n")

    # Build choices for selection
    choices = []
    for state in incomplete:
        next_step = workflow_state_manager.get_next_pending_step(state)
        completed_count = sum(
            1 for s in state.step_states if s.status == StepStatus.COMPLETED
        )
        total_steps = len(state.step_states)

        display_text = f"{state.workflow.name} ({completed_count}/{total_steps} steps done)"
        description = f"ID: {state.id} | Next: Step {next_step} | Dir: {state.working_directory}"
        choices.append(questionary.Choice(display_text, description=description, value=state))

    choices.append(questionary.Separator())
    choices.append(questionary.Choice("Cancel", value="cancel"))

    selected = questionary.select(
        "Select workflow to resume:",
        choices=choices,
        use_shortcuts=True,
        style=questionary.Style(
            [
                ("answer", "fg:#61afef"),
                ("question", "bold"),
                ("instruction", "fg:#98c379"),
            ]
        ),
    ).ask()

    if selected == "cancel" or selected is None:
        return

    resume_workflow(selected)


def resume_workflow(state: WorkflowExecutionState):
    """Resume an incomplete workflow from where it left off."""
    console = Console()

    # Display workflow state overview
    display_workflow_state_overview(console, state)

    next_step_num = workflow_state_manager.get_next_pending_step(state)

    if next_step_num is None:
        rprint("[green]This workflow has no pending steps.[/green]")
        workflow_state_manager.mark_complete(state)
        return

    # Check if we're in the right directory
    if os.getcwd() != state.working_directory:
        rprint(f"\n[yellow]Note: This workflow was started in:[/yellow]")
        rprint(f"[dim]  {state.working_directory}[/dim]")
        rprint(f"[yellow]Current directory:[/yellow]")
        rprint(f"[dim]  {os.getcwd()}[/dim]")

    rprint(f"\n[bold]Resuming from step {next_step_num}...[/bold]")

    # Ask how to proceed
    action = questionary.select(
        "How would you like to continue?",
        choices=[
            questionary.Choice("Run remaining steps sequentially", value="run_all"),
            questionary.Choice("Step through interactively", value="interactive"),
            questionary.Choice("Discard this workflow", value="discard"),
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
        run_workflow_all(state.workflow, state, next_step_num)
    elif action == "interactive":
        run_workflow_interactive(state.workflow, state, next_step_num)
    elif action == "discard":
        workflow_state_manager.delete_state(state.id)
        rprint("[yellow]Workflow discarded.[/yellow]")


def display_workflow_state_overview(console: Console, state: WorkflowExecutionState):
    """Display a workflow's execution state with step statuses."""
    table = Table(
        title=f"Workflow: {state.workflow.name} (ID: {state.id})",
        show_header=True,
        header_style="bold cyan"
    )
    table.add_column("Step", style="dim", width=6)
    table.add_column("Status", width=10)
    table.add_column("Command", style="green")
    table.add_column("Description")

    status_styles = {
        StepStatus.PENDING: "[dim]Pending[/dim]",
        StepStatus.COMPLETED: "[green]Done[/green]",
        StepStatus.FAILED: "[red]Failed[/red]",
        StepStatus.SKIPPED: "[yellow]Skipped[/yellow]",
    }

    for step in state.workflow.steps:
        step_state = workflow_state_manager.get_step_state(state, step.step_number)
        status_display = status_styles.get(step_state.status, str(step_state.status))

        # Add exit code for failed steps
        if step_state.status == StepStatus.FAILED and step_state.exit_code is not None:
            status_display = f"[red]Failed({step_state.exit_code})[/red]"

        table.add_row(
            str(step.step_number),
            status_display,
            step.command,
            step.description
        )

    console.print(table)
    console.print(f"\n[dim]Started: {state.started_at}[/dim]")
    console.print(f"[dim]Last updated: {state.updated_at}[/dim]")
