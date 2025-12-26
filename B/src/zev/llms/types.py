from typing import Optional

from pydantic import BaseModel


class Command(BaseModel):
    command: str
    short_explanation: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None


class WorkflowStep(BaseModel):
    """A single step in a multi-step workflow."""

    step_number: int
    command: str
    short_explanation: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None
    depends_on_previous: bool = True  # If True, only run if previous step succeeded


class Workflow(BaseModel):
    """A multi-step workflow where commands are executed in sequence."""

    workflow_description: str
    steps: list[WorkflowStep]


class OptionsResponse(BaseModel):
    commands: list[Command]
    is_valid: bool
    explanation_if_not_valid: Optional[str] = None
    workflow: Optional[Workflow] = None  # Present when task requires multiple steps
