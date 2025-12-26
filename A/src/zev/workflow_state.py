import uuid
from pathlib import Path
from typing import Optional

import questionary
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from zev.constants import WORKFLOW_STATE_FILE_NAME
from zev.llms.types import (
    StepStatus,
    Workflow,
    WorkflowState,
    WorkflowStepState,
)


class WorkflowStateManager:
    def __init__(self) -> None:
        self.path = Path.home() / WORKFLOW_STATE_FILE_NAME
        self.max_entries = 20
        self.path.touch(exist_ok=True)
        self.encoding = "utf-8"

    def create_workflow_state(self, workflow: Workflow, original_query: str) -> WorkflowState:
        """Create a new workflow state for tracking execution."""
        workflow_id = str(uuid.uuid4())[:8]
        step_states = [
            WorkflowStepState(step_number=step.step_number)
            for step in workflow.steps
        ]
        state = WorkflowState(
            workflow_id=workflow_id,
            workflow=workflow,
            original_query=original_query,
            step_states=step_states,
        )
        return state

    def save_state(self, state: WorkflowState) -> None:
        """Save workflow state to file."""
        # Read existing states
        existing_states = self._read_all_states()

        # Update or add the state
        found = False
        for i, existing in enumerate(existing_states):
            if existing.workflow_id == state.workflow_id:
                existing_states[i] = state
                found = True
                break

        if not found:
            existing_states.append(state)

        # Keep only incomplete workflows and trim to max entries
        # Remove completed workflows older than the most recent ones
        incomplete = [s for s in existing_states if not s.is_complete]
        complete = [s for s in existing_states if s.is_complete]

        # Keep all incomplete and a few recent complete ones for reference
        states_to_save = incomplete + complete[-5:]

        # Trim to max entries
        if len(states_to_save) > self.max_entries:
            states_to_save = states_to_save[-self.max_entries:]

        self._write_all_states(states_to_save)

    def get_incomplete_workflows(self) -> list[WorkflowState]:
        """Get all incomplete workflow states."""
        states = self._read_all_states()
        return [s for s in states if not s.is_complete]

    def get_workflow_by_id(self, workflow_id: str) -> Optional[WorkflowState]:
        """Get a specific workflow state by ID."""
        states = self._read_all_states()
        for state in states:
            if state.workflow_id == workflow_id:
                return state
        return None

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow state."""
        states = self._read_all_states()
        original_count = len(states)
        states = [s for s in states if s.workflow_id != workflow_id]
        if len(states) < original_count:
            self._write_all_states(states)
            return True
        return False

    def _read_all_states(self) -> list[WorkflowState]:
        """Read all workflow states from file."""
        if not self.path.exists():
            return []

        states = []
        with open(self.path, "r", encoding=self.encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        states.append(WorkflowState.model_validate_json(line))
                    except Exception:
                        # Skip invalid lines
                        continue
        return states

    def _write_all_states(self, states: list[WorkflowState]) -> None:
        """Write all workflow states to file."""
        with open(self.path, "w", encoding=self.encoding) as f:
            for state in states:
                f.write(state.model_dump_json() + "\n")


# Global instance
workflow_state_manager = WorkflowStateManager()


def show_incomplete_workflows() -> Optional[WorkflowState]:
    """Display incomplete workflows and let user select one to resume."""
    incomplete = workflow_state_manager.get_incomplete_workflows()

    if not incomplete:
        rprint("[yellow]No incomplete workflows found.[/yellow]")
        return None

    console = Console()

    # Display summary table
    table = Table(title="Incomplete Workflows", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Workflow", style="green")
    table.add_column("Progress")
    table.add_column("Query", max_width=30)
    table.add_column("Last Updated")

    for state in incomplete:
        completed = len([s for s in state.step_states if s.status == StepStatus.COMPLETED])
        total = len(state.step_states)
        failed = len([s for s in state.step_states if s.status == StepStatus.FAILED])
        progress = f"{completed}/{total}"
        if failed > 0:
            progress += f" [red]({failed} failed)[/red]"

        # Truncate query if too long
        query = state.original_query[:27] + "..." if len(state.original_query) > 30 else state.original_query

        table.add_row(
            state.workflow_id,
            state.workflow.name,
            progress,
            query,
            state.updated_at.strftime("%Y-%m-%d %H:%M")
        )

    console.print(table)
    print("")

    # Let user select a workflow
    style = questionary.Style(
        [
            ("answer", "fg:#61afef"),
            ("question", "bold"),
            ("instruction", "fg:#98c379"),
        ]
    )

    choices = [
        questionary.Choice(
            f"{state.workflow_id}: {state.workflow.name}",
            value=state
        )
        for state in incomplete
    ]
    choices.append(questionary.Separator())
    choices.append(questionary.Choice("Cancel", value=None))

    selected = questionary.select(
        "Select a workflow to resume:",
        choices=choices,
        use_shortcuts=True,
        style=style,
    ).ask()

    return selected


def display_workflow_state_details(state: WorkflowState) -> None:
    """Display detailed state of a workflow."""
    console = Console()

    table = Table(title=f"Workflow: {state.workflow.name} ({state.workflow_id})", show_header=True, header_style="bold cyan")
    table.add_column("Step", style="dim", width=6)
    table.add_column("Status", width=10)
    table.add_column("Command", style="green")
    table.add_column("Description")

    for step in state.workflow.steps:
        step_state = next((s for s in state.step_states if s.step_number == step.step_number), None)
        status = step_state.status.value if step_state else "unknown"

        # Color code status
        if status == "completed":
            status_display = "[green]completed[/green]"
        elif status == "failed":
            status_display = "[red]failed[/red]"
        elif status == "skipped":
            status_display = "[yellow]skipped[/yellow]"
        else:
            status_display = "[dim]pending[/dim]"

        table.add_row(
            str(step.step_number),
            status_display,
            step.command,
            step.description
        )

    console.print(table)
    console.print(f"\n[dim]Original query: {state.original_query}[/dim]")
    console.print(f"[dim]Started: {state.started_at.strftime('%Y-%m-%d %H:%M')}[/dim]")
    console.print(f"[dim]Last updated: {state.updated_at.strftime('%Y-%m-%d %H:%M')}[/dim]")
