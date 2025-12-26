from subprocess import run as run_command, CompletedProcess

import questionary
from rich import print as rprint
from rich.panel import Panel

from zev.llms.types import Workflow, WorkflowStep


def show_workflow(workflow: Workflow):
    """Display the workflow and let user choose to execute it."""
    display_workflow_summary(workflow)
    if questionary.confirm("Execute this workflow?").ask():
        execute_workflow(workflow)


def display_workflow_summary(workflow: Workflow):
    """Display a summary of the workflow steps."""
    rprint(f"\n[bold cyan]Workflow:[/bold cyan] {workflow.workflow_description}\n")
    rprint(f"[dim]This workflow has {len(workflow.steps)} step(s):[/dim]\n")

    for step in workflow.steps:
        step_prefix = f"[bold]Step {step.step_number}:[/bold]"
        danger_indicator = " [red](dangerous)[/red]" if step.is_dangerous else ""
        dependency_info = ""
        if step.step_number > 1 and step.depends_on_previous:
            dependency_info = " [dim](depends on previous step)[/dim]"

        rprint(f"  {step_prefix}{danger_indicator}{dependency_info}")
        rprint(f"    [cyan]{step.command}[/cyan]")
        rprint(f"    [dim]{step.short_explanation}[/dim]")
        if step.dangerous_explanation:
            rprint(f"    [red]Warning: {step.dangerous_explanation}[/red]")
        print()


def execute_workflow(workflow: Workflow):
    """Execute the workflow steps in sequence."""
    rprint("\n[bold]Starting workflow execution...[/bold]\n")

    results: list[tuple[WorkflowStep, bool, str]] = []  # (step, success, output)

    for i, step in enumerate(workflow.steps):
        # Check if we should skip due to dependency failure
        if step.depends_on_previous and i > 0:
            prev_success = results[-1][1] if results else True
            if not prev_success:
                rprint(
                    f"[yellow]⏭ Skipping step {step.step_number}: "
                    f"Previous step failed and this step depends on it[/yellow]\n"
                )
                results.append((step, False, "Skipped due to dependency failure"))
                continue

        # Show step info
        rprint(f"[bold cyan]Step {step.step_number}/{len(workflow.steps)}:[/bold cyan] {step.short_explanation}")
        rprint(f"  [dim]Command:[/dim] {step.command}")

        # Handle dangerous steps
        if step.is_dangerous:
            rprint(f"  [red]⚠️ Warning: {step.dangerous_explanation}[/red]")
            if not questionary.confirm("  This step is dangerous. Continue?", default=False).ask():
                rprint(f"  [yellow]⏭ Step {step.step_number} skipped by user[/yellow]\n")
                results.append((step, False, "Skipped by user"))
                continue

        # Confirm execution
        if not questionary.confirm("  Run this step?", default=True).ask():
            rprint(f"  [yellow]⏭ Step {step.step_number} skipped by user[/yellow]\n")
            results.append((step, False, "Skipped by user"))
            continue

        # Execute the step
        try:
            rprint(f"  [dim]Executing...[/dim]")
            result: CompletedProcess = run_command(step.command, shell=True, capture_output=False)

            if result.returncode == 0:
                rprint(f"  [green]✓ Step {step.step_number} completed successfully[/green]\n")
                results.append((step, True, "Success"))
            else:
                rprint(f"  [red]✗ Step {step.step_number} failed (exit code: {result.returncode})[/red]\n")
                results.append((step, False, f"Failed with exit code {result.returncode}"))

                # Ask if user wants to continue
                if i < len(workflow.steps) - 1:
                    if not questionary.confirm("  Continue with remaining steps?", default=True).ask():
                        rprint("[yellow]Workflow execution stopped by user[/yellow]\n")
                        break
        except Exception as e:
            rprint(f"  [red]✗ Step {step.step_number} failed with error: {e}[/red]\n")
            results.append((step, False, str(e)))

            if i < len(workflow.steps) - 1:
                if not questionary.confirm("  Continue with remaining steps?", default=True).ask():
                    rprint("[yellow]Workflow execution stopped by user[/yellow]\n")
                    break

    # Display summary
    display_execution_summary(workflow, results)


def display_execution_summary(workflow: Workflow, results: list[tuple[WorkflowStep, bool, str]]):
    """Display a summary of the workflow execution."""
    successful = sum(1 for _, success, _ in results if success)
    failed = sum(1 for _, success, _ in results if not success)
    total = len(workflow.steps)

    rprint("\n[bold]Workflow Execution Summary:[/bold]")
    rprint(f"  Total steps: {total}")
    rprint(f"  [green]Completed: {successful}[/green]")
    if failed > 0:
        rprint(f"  [red]Failed/Skipped: {failed}[/red]")

    if successful == total:
        rprint("\n[bold green]✓ Workflow completed successfully![/bold green]")
    elif successful > 0:
        rprint("\n[bold yellow]⚠ Workflow partially completed[/bold yellow]")
    else:
        rprint("\n[bold red]✗ Workflow failed[/bold red]")
