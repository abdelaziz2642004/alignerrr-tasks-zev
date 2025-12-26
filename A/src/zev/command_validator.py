import re
import shlex
import subprocess
from typing import Optional

from zev.llms.types import Command, OptionsResponse


class CommandValidationError:
    """Represents a validation error for a command."""

    def __init__(self, command: str, error_type: str, message: str):
        self.command = command
        self.error_type = error_type
        self.message = message


class CommandValidator:
    """Validates shell commands for syntax errors and malformed constructs."""

    # Patterns that indicate malformed or incomplete commands
    MALFORMED_PATTERNS = [
        (r"^\s*\|\s*$", "Empty pipe"),
        (r"^\s*\|", "Command starts with pipe"),
        (r"\|\s*$", "Command ends with pipe"),
        # Semicolon at end is invalid unless escaped (like in find -exec \;)
        (r"(?<!\\);\s*$", "Command ends with semicolon without following command"),
        (r"^\s*;\s*", "Command starts with semicolon"),
        (r"\|\s*\|(?!\|)", "Empty command between pipes"),
        (r"&&\s*$", "Command ends with &&"),
        (r"^\s*&&", "Command starts with &&"),
        (r"\|\|\s*$", "Command ends with ||"),
        (r"^\s*\|\|", "Command starts with ||"),
        (r">\s*$", "Redirect without target"),
        (r"<\s*$", "Input redirect without source"),
        (r">>\s*$", "Append redirect without target"),
    ]

    # Patterns for unclosed quotes and brackets
    UNCLOSED_PATTERNS = [
        (r"(?<!\\)`(?:[^`\\]|\\.)*$", "Unclosed backtick"),
    ]

    def __init__(self):
        self._compiled_malformed = [
            (re.compile(pattern), msg) for pattern, msg in self.MALFORMED_PATTERNS
        ]
        self._compiled_unclosed = [
            (re.compile(pattern), msg) for pattern, msg in self.UNCLOSED_PATTERNS
        ]

    def validate_command(self, command: str) -> Optional[CommandValidationError]:
        """
        Validate a single command string.

        Returns None if the command is valid, or a CommandValidationError if invalid.
        """
        if not command or not command.strip():
            return CommandValidationError(command, "empty", "Empty command")

        # Check for malformed patterns
        for pattern, message in self._compiled_malformed:
            if pattern.search(command):
                return CommandValidationError(command, "malformed", message)

        # Check for unclosed patterns
        for pattern, message in self._compiled_unclosed:
            if pattern.search(command):
                return CommandValidationError(command, "unclosed", message)

        # Use shlex to check for quote balancing
        quote_error = self._check_quotes(command)
        if quote_error:
            return quote_error

        # Use shell syntax check if available
        syntax_error = self._check_shell_syntax(command)
        if syntax_error:
            return syntax_error

        return None

    def _check_quotes(self, command: str) -> Optional[CommandValidationError]:
        """Check for unbalanced quotes using shlex."""
        try:
            shlex.split(command)
            return None
        except ValueError as e:
            error_msg = str(e)
            if "No closing quotation" in error_msg:
                return CommandValidationError(command, "unclosed_quote", "Unclosed quotation mark")
            elif "No escaped character" in error_msg:
                return CommandValidationError(command, "escape_error", "Invalid escape sequence")
            return CommandValidationError(command, "parse_error", f"Quote parsing error: {error_msg}")

    def _check_shell_syntax(self, command: str) -> Optional[CommandValidationError]:
        """
        Use bash -n to check shell syntax without executing.

        This only checks for basic syntax errors and won't catch all issues,
        but it's a good additional validation layer.
        """
        try:
            result = subprocess.run(
                ["bash", "-n", "-c", command],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                # Extract the relevant part of the error message
                if error_msg:
                    # Remove the "bash: -c: line X:" prefix if present
                    cleaned_msg = re.sub(r"^bash: -c: line \d+: ", "", error_msg)
                    cleaned_msg = re.sub(r"^bash: line \d+: ", "", cleaned_msg)
                    return CommandValidationError(
                        command, "syntax_error", f"Shell syntax error: {cleaned_msg}"
                    )
                return CommandValidationError(command, "syntax_error", "Shell syntax error")
            return None
        except subprocess.TimeoutExpired:
            # If syntax check times out, we skip this validation
            return None
        except FileNotFoundError:
            # bash not available, skip this check
            return None
        except Exception:
            # Any other error, skip this check
            return None

    def is_valid(self, command: str) -> bool:
        """Return True if the command is valid, False otherwise."""
        return self.validate_command(command) is None

    def validate_commands(self, commands: list[Command]) -> list[Command]:
        """
        Validate a list of Command objects and return only the valid ones.

        Invalid commands are filtered out.
        """
        valid_commands = []
        for cmd in commands:
            if self.is_valid(cmd.command):
                valid_commands.append(cmd)
        return valid_commands

    def validate_options_response(self, response: OptionsResponse) -> OptionsResponse:
        """
        Validate an OptionsResponse and return a new one with only valid commands.

        If all commands are invalid, the response will have an empty commands list.
        """
        if not response.commands:
            return response

        valid_commands = self.validate_commands(response.commands)

        return OptionsResponse(
            commands=valid_commands,
            is_valid=response.is_valid,
            explanation_if_not_valid=response.explanation_if_not_valid,
        )


# Global validator instance for convenience
_validator = CommandValidator()


def validate_command(command: str) -> Optional[CommandValidationError]:
    """Validate a single command string."""
    return _validator.validate_command(command)


def is_valid_command(command: str) -> bool:
    """Return True if the command is valid, False otherwise."""
    return _validator.is_valid(command)


def validate_commands(commands: list[Command]) -> list[Command]:
    """Validate a list of Command objects and return only the valid ones."""
    return _validator.validate_commands(commands)


def validate_options_response(response: OptionsResponse) -> OptionsResponse:
    """Validate an OptionsResponse and return a new one with only valid commands."""
    return _validator.validate_options_response(response)
