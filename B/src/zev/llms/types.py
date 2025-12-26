from enum import Enum
from typing import Optional

from pydantic import BaseModel


class CommandFeedback(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class Command(BaseModel):
    command: str
    short_explanation: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None
    feedback: Optional[CommandFeedback] = None


class OptionsResponse(BaseModel):
    commands: list[Command]
    is_valid: bool
    explanation_if_not_valid: Optional[str] = None
