from typing import Optional

from pydantic import BaseModel, field_validator

from zev.command_validator import validate_command


class Command(BaseModel):
    command: str
    short_explanation: str
    is_dangerous: bool
    dangerous_explanation: Optional[str] = None

    @field_validator("command")
    @classmethod
    def validate_command_syntax(cls, v: str) -> str:
        """Validate that the command has valid shell syntax."""
        result = validate_command(v)
        if not result.is_valid:
            raise ValueError(f"Invalid command syntax: {result.error_message}")
        return v


class OptionsResponse(BaseModel):
    commands: list[Command]
    is_valid: bool
    explanation_if_not_valid: Optional[str] = None
