from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import uuid

from pydantic import BaseModel

from zev.constants import WORKFLOW_STATE_FILE_NAME
from zev.llms.types import Workflow, WorkflowStep


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStepState(BaseModel):
    step_number: int
    status: StepStatus = StepStatus.PENDING
    exit_code: Optional[int] = None


class WorkflowExecutionState(BaseModel):
    id: str
    workflow: Workflow
    step_states: list[WorkflowStepState]
    started_at: str
    updated_at: str
    working_directory: str
    is_complete: bool = False


class WorkflowStateManager:
    def __init__(self) -> None:
        self.path = Path.home() / WORKFLOW_STATE_FILE_NAME
        self.max_entries = 20
        self.path.touch(exist_ok=True)
        self.encoding = "utf-8"

    def create_execution_state(self, workflow: Workflow, working_dir: str) -> WorkflowExecutionState:
        now = datetime.now().isoformat()
        step_states = [
            WorkflowStepState(step_number=step.step_number)
            for step in workflow.steps
        ]
        state = WorkflowExecutionState(
            id=str(uuid.uuid4())[:8],
            workflow=workflow,
            step_states=step_states,
            started_at=now,
            updated_at=now,
            working_directory=working_dir,
        )
        self._save_state(state)
        return state

    def update_step_status(
        self,
        state: WorkflowExecutionState,
        step_number: int,
        status: StepStatus,
        exit_code: Optional[int] = None
    ) -> WorkflowExecutionState:
        for step_state in state.step_states:
            if step_state.step_number == step_number:
                step_state.status = status
                step_state.exit_code = exit_code
                break
        state.updated_at = datetime.now().isoformat()

        # Check if workflow is complete
        all_done = all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED)
            for s in state.step_states
        )
        if all_done:
            state.is_complete = True

        self._save_state(state)
        return state

    def mark_complete(self, state: WorkflowExecutionState) -> None:
        state.is_complete = True
        state.updated_at = datetime.now().isoformat()
        self._save_state(state)

    def get_incomplete_workflows(self) -> list[WorkflowExecutionState]:
        all_states = self._load_all_states()
        return [s for s in all_states if not s.is_complete]

    def get_state_by_id(self, state_id: str) -> Optional[WorkflowExecutionState]:
        all_states = self._load_all_states()
        for state in all_states:
            if state.id == state_id:
                return state
        return None

    def get_next_pending_step(self, state: WorkflowExecutionState) -> Optional[int]:
        for step_state in state.step_states:
            if step_state.status == StepStatus.PENDING:
                return step_state.step_number
        return None

    def get_step_state(self, state: WorkflowExecutionState, step_number: int) -> Optional[WorkflowStepState]:
        for step_state in state.step_states:
            if step_state.step_number == step_number:
                return step_state
        return None

    def delete_state(self, state_id: str) -> None:
        all_states = self._load_all_states()
        all_states = [s for s in all_states if s.id != state_id]
        self._write_all_states(all_states)

    def _save_state(self, state: WorkflowExecutionState) -> None:
        all_states = self._load_all_states()
        # Update existing or add new
        found = False
        for i, s in enumerate(all_states):
            if s.id == state.id:
                all_states[i] = state
                found = True
                break
        if not found:
            all_states.append(state)

        # Trim old completed workflows if exceeding max
        incomplete = [s for s in all_states if not s.is_complete]
        complete = [s for s in all_states if s.is_complete]
        if len(all_states) > self.max_entries:
            # Keep all incomplete and most recent complete
            keep_complete = complete[-(self.max_entries - len(incomplete)):]
            all_states = incomplete + keep_complete

        self._write_all_states(all_states)

    def _load_all_states(self) -> list[WorkflowExecutionState]:
        try:
            with open(self.path, "r", encoding=self.encoding) as f:
                return [WorkflowExecutionState.model_validate_json(line) for line in f if line.strip()]
        except Exception:
            return []

    def _write_all_states(self, states: list[WorkflowExecutionState]) -> None:
        with open(self.path, "w", encoding=self.encoding) as f:
            for state in states:
                f.write(state.model_dump_json() + "\n")


# Singleton instance
workflow_state_manager = WorkflowStateManager()
