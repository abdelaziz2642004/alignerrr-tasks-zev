from subprocess import run as run_command
from typing import Optional

import pyperclip
import questionary
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from zev.llms.types import Command, StepStatus, Workflow, WorkflowState


# Global reference to workflow state manager (lazy loaded to avoid circular imports)
_workflow_state_manager = None


def _get_workflow_state_manager():
    global _workflow_state_manager
    if _workflow_state_manager is None:
        from zev.workflow_state import workflow_state_manager
        _workflow_state_manager = workflow_state_manager
    return _workflow_state_manager


def show_options(commands: list[Command], workflows: list[Workflow] = None, original_query: str = ""):
    workflows = workflows or []
    options = assemble_options(commands, workflows)
    selected = display_options(options)
    handle_selected_option(selected, original_query)


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


def handle_selected_option(selected, original_query: str = ""):
    if selected and selected != "Cancel":
        print("")
        if isinstance(selected, Workflow):
            handle_workflow(selected, original_query)
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


def handle_workflow(workflow: Workflow, original_query: str = ""):
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
        run_workflow_all(workflow, original_query)
    elif action == "copy_all":
        copy_workflow_commands(workflow)
    elif action == "interactive":
        run_workflow_interactive(workflow, original_query)


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


def run_workflow_all(workflow: Workflow, original_query: str = "", state: Optional[WorkflowState] = None, start_from_step: int = 1):
    manager = _get_workflow_state_manager()

    # Create state if not provided (new workflow execution)
    if state is None:
        state = manager.create_workflow_state(workflow, original_query)

    rprint("\n[bold cyan]Running workflow...[/bold cyan]\n")

    for step in workflow.steps:
        # Skip already completed steps when resuming
        if step.step_number < start_from_step:
            continue

        rprint(f"[bold]Step {step.step_number}:[/bold] {step.description}")
        rprint(f"[dim]$ {step.command}[/dim]")

        if step.is_dangerous and step.dangerous_explanation:
            rprint(f"[red]Warning: {step.dangerous_explanation}[/red]")
            if not questionary.confirm("Continue with this dangerous step?").ask():
                rprint("[yellow]Workflow aborted by user.[/yellow]")
                manager.save_state(state)
                rprint(f"[dim]Workflow state saved. Resume with: zev --resume[/dim]")
                return

        result = run_command(step.command, shell=True)

        if result.returncode != 0:
            state.mark_step_failed(step.step_number, result.returncode)
            manager.save_state(state)
            rprint(f"[red]Step {step.step_number} failed with exit code {result.returncode}[/red]")

            next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
            if next_step and next_step.depends_on_previous:
                rprint("[yellow]Stopping workflow because next step depends on this one.[/yellow]")
                rprint(f"[dim]Workflow state saved. Resume with: zev --resume[/dim]")
                return
            elif not questionary.confirm("Continue with remaining steps?").ask():
                rprint("[yellow]Workflow aborted by user.[/yellow]")
                rprint(f"[dim]Workflow state saved. Resume with: zev --resume[/dim]")
                return
        else:
            state.mark_step_completed(step.step_number, result.returncode)
            manager.save_state(state)
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


def run_workflow_interactive(workflow: Workflow, original_query: str = "", state: Optional[WorkflowState] = None, start_from_step: int = 1):
    manager = _get_workflow_state_manager()

    # Create state if not provided (new workflow execution)
    if state is None:
        state = manager.create_workflow_state(workflow, original_query)

    rprint("\n[bold cyan]Interactive workflow mode[/bold cyan]")
    rprint("[dim]You will be prompted before each step.[/dim]\n")

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
                questionary.Choice("Abort workflow (save progress)", value="abort"),
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
            manager.save_state(state)
            rprint("[yellow]Workflow aborted by user.[/yellow]")
            rprint(f"[dim]Workflow state saved. Resume with: zev --resume[/dim]")
            return
        elif action == "skip":
            state.mark_step_skipped(step.step_number)
            manager.save_state(state)
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
            # Don't continue to next step when copying, let user decide
            # Re-prompt for the same step
            continue
        elif action == "run":
            result = run_command(step.command, shell=True)
            if result.returncode != 0:
                state.mark_step_failed(step.step_number, result.returncode)
                manager.save_state(state)
                rprint(f"[red]Step failed with exit code {result.returncode}[/red]")
                next_step = next((s for s in workflow.steps if s.step_number == step.step_number + 1), None)
                if next_step and next_step.depends_on_previous:
                    rprint("[yellow]Warning: Next step depends on this one![/yellow]")
            else:
                state.mark_step_completed(step.step_number, result.returncode)
                manager.save_state(state)
                rprint(f"[green]✓[/green] Step {step.step_number} completed")

    rprint("\n[bold green]Interactive workflow completed![/bold green]")


def resume_workflow(state: WorkflowState):
    """Resume a workflow from its saved state."""
    from zev.workflow_state import display_workflow_state_details

    console = Console()

    # Display current state
    display_workflow_state_details(state)

    next_step = state.get_next_pending_step()
    if next_step is None:
        rprint("\n[green]This workflow is already complete![/green]")
        return

    # Check if there's a failed step that needs retry
    failed_steps = [s for s in state.step_states if s.status == StepStatus.FAILED]
    if failed_steps:
        rprint(f"\n[yellow]Note: Step(s) {', '.join(str(s.step_number) for s in failed_steps)} failed previously.[/yellow]")

    rprint(f"\n[cyan]Will resume from step {next_step}[/cyan]")

    # Ask user what they want to do
    action = questionary.select(
        "\nHow would you like to resume?",
        choices=[
            questionary.Choice("Run remaining steps sequentially", value="run_all"),
            questionary.Choice("Step through interactively", value="interactive"),
            questionary.Choice("Retry failed step(s) first", value="retry") if failed_steps else None,
            questionary.Choice("Discard workflow and cancel", value="discard"),
            questionary.Choice("Cancel (keep saved state)", value="cancel"),
        ],
        style=questionary.Style(
            [
                ("answer", "fg:#61afef"),
                ("question", "bold"),
                ("instruction", "fg:#98c379"),
            ]
        ),
    ).ask()

    if action == "cancel":
        rprint("[dim]Workflow state preserved. Resume later with: zev --resume[/dim]")
        return
    elif action == "discard":
        manager = _get_workflow_state_manager()
        manager.delete_workflow(state.workflow_id)
        rprint("[yellow]Workflow discarded.[/yellow]")
        return
    elif action == "retry":
        # Reset failed steps to pending and resume from first failed
        first_failed = min(s.step_number for s in failed_steps)
        for step_state in state.step_states:
            if step_state.status == StepStatus.FAILED:
                step_state.status = StepStatus.PENDING
                step_state.exit_code = None
        run_workflow_interactive(state.workflow, state.original_query, state, first_failed)
    elif action == "run_all":
        run_workflow_all(state.workflow, state.original_query, state, next_step)
    elif action == "interactive":
        run_workflow_interactive(state.workflow, state.original_query, state, next_step)
