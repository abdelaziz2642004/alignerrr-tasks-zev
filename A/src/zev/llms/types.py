from typing import Optional

from pydantic import BaseModel


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
