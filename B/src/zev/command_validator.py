"""Command validation module for checking shell command syntax and safety."""

import re
import shlex
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Result of command validation."""

    is_valid: bool
    error_message: Optional[str] = None


class CommandValidator:
    """Validates shell commands for syntax errors and malformed constructs."""

    # Patterns for detecting malformed shell constructs
    UNCLOSED_QUOTES_PATTERN = re.compile(r"""^(?:[^"'\\]|\\.)*(?:"(?:[^"\\]|\\.)*$|'[^']*$)""")

    # Common shell operators that need proper usage
    PIPE_OPERATORS = ["|", "||", "&&"]
    REDIRECT_OPERATORS = [">", ">>", "<", "<<", "2>", "2>>", "&>", "&>>"]

    # Dangerous patterns that indicate incomplete/malformed commands
    TRAILING_OPERATORS = re.compile(r"[|&><;]\s*$")
    LEADING_OPERATORS = re.compile(r"^\s*[|&]")

    # Empty or whitespace-only command pattern
    EMPTY_PATTERN = re.compile(r"^\s*$")

    # Unbalanced parentheses/braces patterns
    SUBSHELL_OPEN = re.compile(r"\(")
    SUBSHELL_CLOSE = re.compile(r"\)")
    BRACE_OPEN = re.compile(r"\{")
    BRACE_CLOSE = re.compile(r"\}")
    BRACKET_OPEN = re.compile(r"\[")
    BRACKET_CLOSE = re.compile(r"\]")

    def validate(self, command: str) -> ValidationResult:
        """
        Validate a shell command for syntax errors and malformed constructs.

        Args:
            command: The shell command string to validate.

        Returns:
            ValidationResult indicating if the command is valid and any error message.
        """
        if command is None:
            return ValidationResult(is_valid=False, error_message="Command is None")

        # Check for empty command
        if self.EMPTY_PATTERN.match(command):
            return ValidationResult(is_valid=False, error_message="Command is empty or whitespace-only")

        # Check for unclosed quotes using shlex
        quote_result = self._check_quotes(command)
        if not quote_result.is_valid:
            return quote_result

        # Check for trailing operators (incomplete pipes/redirects)
        if self.TRAILING_OPERATORS.search(command):
            return ValidationResult(
                is_valid=False, error_message="Command ends with incomplete operator (pipe, redirect, or semicolon)"
            )

        # Check for leading pipe/ampersand operators
        if self.LEADING_OPERATORS.match(command):
            return ValidationResult(
                is_valid=False, error_message="Command starts with invalid operator (pipe or ampersand)"
            )

        # Check for balanced parentheses/braces
        balance_result = self._check_balanced_delimiters(command)
        if not balance_result.is_valid:
            return balance_result

        # Check for empty pipe segments
        pipe_result = self._check_pipe_segments(command)
        if not pipe_result.is_valid:
            return pipe_result

        # Check for malformed redirections
        redirect_result = self._check_redirections(command)
        if not redirect_result.is_valid:
            return redirect_result

        # Check for obviously broken command structures
        structure_result = self._check_command_structure(command)
        if not structure_result.is_valid:
            return structure_result

        return ValidationResult(is_valid=True)

    def _check_quotes(self, command: str) -> ValidationResult:
        """Check for unclosed quotes using shlex."""
        try:
            # shlex.split will raise ValueError on unclosed quotes
            shlex.split(command)
            return ValidationResult(is_valid=True)
        except ValueError as e:
            error_msg = str(e)
            if "No closing quotation" in error_msg or "No escaped character" in error_msg:
                return ValidationResult(is_valid=False, error_message=f"Unclosed quote in command: {error_msg}")
            # Re-raise unexpected errors
            return ValidationResult(is_valid=False, error_message=f"Quote parsing error: {error_msg}")

    def _check_balanced_delimiters(self, command: str) -> ValidationResult:
        """Check for balanced parentheses, braces, and brackets."""
        # Simple counting approach - doesn't account for quotes but catches obvious issues
        # We need to be careful about quotes, so we'll use a state machine

        in_single_quote = False
        in_double_quote = False
        escaped = False
        paren_count = 0
        brace_count = 0
        bracket_count = 0

        for char in command:
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                continue

            if in_single_quote or in_double_quote:
                continue

            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
                if paren_count < 0:
                    return ValidationResult(is_valid=False, error_message="Unmatched closing parenthesis")
            elif char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count < 0:
                    return ValidationResult(is_valid=False, error_message="Unmatched closing brace")
            elif char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count < 0:
                    return ValidationResult(is_valid=False, error_message="Unmatched closing bracket")

        if paren_count > 0:
            return ValidationResult(is_valid=False, error_message="Unclosed parenthesis")
        if brace_count > 0:
            return ValidationResult(is_valid=False, error_message="Unclosed brace")
        if bracket_count > 0:
            return ValidationResult(is_valid=False, error_message="Unclosed bracket")

        return ValidationResult(is_valid=True)

    def _check_pipe_segments(self, command: str) -> ValidationResult:
        """Check for empty segments in pipe chains."""
        # Split by pipe, but be careful about || (or operator)
        # We need to handle this more carefully

        # Simple check: look for patterns like "| |" or "||" followed by nothing meaningful
        if re.search(r"\|\s*\|(?!\|)", command):
            # This catches "| |" but not "||" which is valid
            pass

        # Check for empty pipe segment: "cmd |  | cmd" or "| cmd"
        if re.search(r"\|\s*\|", command):
            return ValidationResult(is_valid=False, error_message="Empty pipe segment detected")

        # Check for command starting with just a pipe (not ||)
        if re.match(r"^\s*\|(?!\|)", command):
            return ValidationResult(is_valid=False, error_message="Command cannot start with a pipe")

        return ValidationResult(is_valid=True)

    def _check_redirections(self, command: str) -> ValidationResult:
        """Check for malformed redirections."""
        # Check for redirections without targets: ">" at end, or "> >" patterns
        # Pattern: redirection operator followed by another operator or end of string

        # Check for consecutive redirects without files between them
        if re.search(r">\s*>(?!>)", command):
            # This is tricky - ">>" is valid, but "> >" is not
            # Actually "> >" could be valid in some cases, let's be lenient
            pass

        # Check for redirection at end without target (already covered by trailing operator check)
        # Check for "< <" which is invalid (not the same as <<)
        if re.search(r"<\s+<(?!<)", command):
            return ValidationResult(is_valid=False, error_message="Malformed input redirection")

        return ValidationResult(is_valid=True)

    def _check_command_structure(self, command: str) -> ValidationResult:
        """Check for obviously broken command structures."""
        # Check for semicolon at start
        if re.match(r"^\s*;", command):
            return ValidationResult(is_valid=False, error_message="Command cannot start with semicolon")

        # Check for multiple consecutive semicolons (usually a mistake)
        if re.search(r";\s*;", command):
            return ValidationResult(is_valid=False, error_message="Multiple consecutive semicolons")

        # Check for && or || at start
        if re.match(r"^\s*&&", command) or re.match(r"^\s*\|\|", command):
            return ValidationResult(
                is_valid=False, error_message="Command cannot start with && or ||"
            )

        # Check for broken variable assignments like "= value" without variable name
        if re.match(r"^\s*=", command):
            return ValidationResult(
                is_valid=False, error_message="Invalid variable assignment (missing variable name)"
            )

        return ValidationResult(is_valid=True)


# Singleton instance for convenience
_validator = CommandValidator()


def validate_command(command: str) -> ValidationResult:
    """
    Validate a shell command for syntax errors and malformed constructs.

    Args:
        command: The shell command string to validate.

    Returns:
        ValidationResult indicating if the command is valid and any error message.
    """
    return _validator.validate(command)
