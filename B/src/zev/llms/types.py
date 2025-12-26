from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Command(BaseModel):
    command: str
    short_explanation: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None


class WorkflowStep(BaseModel):
    step_number: int
    command: str
    description: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None
    depends_on_previous: bool = True


class Workflow(BaseModel):
    name: str
    description: str
    steps: list[WorkflowStep]
    is_dangerous: bool


class OptionsResponse(BaseModel):
    commands: list[Command]
    workflows: list[Workflow] = []
    is_valid: bool
    explanation_if_not_valid: Optional[str] = None


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStepState(BaseModel):
    step_number: int
    status: StepStatus = StepStatus.PENDING
    exit_code: Optional[int] = None


class WorkflowState(BaseModel):
    workflow_id: str
    workflow: Workflow
    original_query: str
    step_states: list[WorkflowStepState]
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_complete: bool = False

    def get_next_pending_step(self) -> Optional[int]:
        """Returns the step number of the next pending step, or None if all done."""
        for state in self.step_states:
            if state.status == StepStatus.PENDING:
                return state.step_number
        return None

    def get_completed_steps(self) -> list[int]:
        """Returns list of completed step numbers."""
        return [s.step_number for s in self.step_states if s.status == StepStatus.COMPLETED]

    def mark_step_completed(self, step_number: int, exit_code: int = 0):
        """Mark a step as completed."""
        for state in self.step_states:
            if state.step_number == step_number:
                state.status = StepStatus.COMPLETED
                state.exit_code = exit_code
                break
        self.updated_at = datetime.now()
        self._check_completion()

    def mark_step_failed(self, step_number: int, exit_code: int):
        """Mark a step as failed."""
        for state in self.step_states:
            if state.step_number == step_number:
                state.status = StepStatus.FAILED
                state.exit_code = exit_code
                break
        self.updated_at = datetime.now()

    def mark_step_skipped(self, step_number: int):
        """Mark a step as skipped."""
        for state in self.step_states:
            if state.step_number == step_number:
                state.status = StepStatus.SKIPPED
                break
        self.updated_at = datetime.now()
        self._check_completion()

    def _check_completion(self):
        """Check if all steps are done (completed or skipped)."""
        self.is_complete = all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.step_states
        )
