"""Command validation module for checking shell command syntax and safety."""

import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


class ValidationErrorCode(Enum):
    """Categorized error codes for command validation failures."""

    EMPTY_COMMAND = "empty_command"
    UNCLOSED_SINGLE_QUOTE = "unclosed_single_quote"
    UNCLOSED_DOUBLE_QUOTE = "unclosed_double_quote"
    UNCLOSED_BACKTICK = "unclosed_backtick"
    TRAILING_PIPE = "trailing_pipe"
    TRAILING_AND = "trailing_and"
    TRAILING_OR = "trailing_or"
    TRAILING_REDIRECT = "trailing_redirect"
    TRAILING_SEMICOLON = "trailing_semicolon"
    TRAILING_BACKSLASH = "trailing_backslash"
    LEADING_PIPE = "leading_pipe"
    LEADING_AND = "leading_and"
    LEADING_OR = "leading_or"
    LEADING_SEMICOLON = "leading_semicolon"
    UNCLOSED_PARENTHESIS = "unclosed_parenthesis"
    UNCLOSED_BRACE = "unclosed_brace"
    UNCLOSED_BRACKET = "unclosed_bracket"
    UNMATCHED_PARENTHESIS = "unmatched_parenthesis"
    UNMATCHED_BRACE = "unmatched_brace"
    UNMATCHED_BRACKET = "unmatched_bracket"
    EMPTY_PIPE_SEGMENT = "empty_pipe_segment"
    EMPTY_AND_SEGMENT = "empty_and_segment"
    EMPTY_OR_SEGMENT = "empty_or_segment"
    CONSECUTIVE_SEMICOLONS = "consecutive_semicolons"
    INVALID_VARIABLE_ASSIGNMENT = "invalid_variable_assignment"
    REDIRECT_WITHOUT_TARGET = "redirect_without_target"
    UNCLOSED_SUBSHELL = "unclosed_subshell"
    UNCLOSED_COMMAND_SUBSTITUTION = "unclosed_command_substitution"
    UNMATCHED_IF_THEN_FI = "unmatched_if_then_fi"
    UNMATCHED_FOR_DO_DONE = "unmatched_for_do_done"
    UNMATCHED_WHILE_DO_DONE = "unmatched_while_do_done"
    UNMATCHED_CASE_ESAC = "unmatched_case_esac"
    PARSE_ERROR = "parse_error"


@dataclass
class ValidationResult:
    """Result of command validation with detailed error information."""

    is_valid: bool
    error_message: Optional[str] = None
    error_code: Optional[ValidationErrorCode] = None
    error_position: Optional[int] = None
    suggestion: Optional[str] = None

    def __str__(self) -> str:
        if self.is_valid:
            return "Valid command"
        parts = [self.error_message or "Unknown error"]
        if self.error_position is not None:
            parts.append(f"(at position {self.error_position})")
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " ".join(parts)

    def print_styled(self, console: Optional[Console] = None) -> None:
        """Print the validation result with Rich styling."""
        if console is None:
            console = Console()

        if self.is_valid:
            console.print("[green]✓[/green] Command is valid")
            return

        # Build styled error message
        error_text = Text()
        error_text.append("✗ ", style="bold red")
        error_text.append(self.error_message or "Unknown error", style="red")

        if self.error_position is not None:
            error_text.append(f" (position {self.error_position})", style="dim")

        console.print(error_text)

        if self.suggestion:
            suggestion_text = Text()
            suggestion_text.append("  → ", style="yellow")
            suggestion_text.append(self.suggestion, style="italic yellow")
            console.print(suggestion_text)

    def to_panel(self, command: Optional[str] = None) -> Panel:
        """Return error as a Rich Panel for display."""
        content = Text()

        if command:
            content.append("Command: ", style="bold")
            content.append(f"{command}\n\n", style="cyan")

        content.append("Error: ", style="bold red")
        content.append(self.error_message or "Unknown error", style="red")

        if self.error_position is not None:
            content.append(f"\nPosition: {self.error_position}", style="dim")

        if self.suggestion:
            content.append("\n\nSuggestion: ", style="bold yellow")
            content.append(self.suggestion, style="yellow")

        return Panel(
            content,
            title="[red]Validation Error[/red]",
            border_style="red",
            expand=False,
        )


# Pre-compiled regex patterns for performance
class _CompiledPatterns:
    """Pre-compiled regex patterns for command validation."""

    # Trailing operator patterns
    TRAILING_REDIRECT = re.compile(r"[<>]+\s*$")

    # Redirection validation patterns
    INVALID_INPUT_REDIRECT = re.compile(r"<\s+<(?!<)")
    INVALID_OUTPUT_REDIRECT = re.compile(r">\s+>(?!>)")

    # Semicolon patterns
    CONSECUTIVE_SEMICOLONS = re.compile(r";\s*;")
    TRIPLE_SEMICOLONS = re.compile(r";;;+")

    # Variable assignment pattern
    INVALID_VAR_ASSIGNMENT = re.compile(r"^\s*=")


# Singleton patterns instance
_patterns = _CompiledPatterns()


class CommandValidator:
    """Validates shell commands for syntax errors and malformed constructs."""

    # Shell control flow keywords that must be balanced
    CONTROL_KEYWORDS = {
        "if": "fi",
        "then": None,
        "elif": None,
        "else": None,
        "fi": "if",
        "for": "done",
        "while": "done",
        "until": "done",
        "do": None,
        "done": ("for", "while", "until"),
        "case": "esac",
        "esac": "case",
        "select": "done",
    }

    def __init__(self) -> None:
        """Initialize the validator with pre-compiled patterns."""
        self._patterns = _patterns

    def validate(self, command: str) -> ValidationResult:
        """
        Validate a shell command for syntax errors and malformed constructs.

        Args:
            command: The shell command string to validate.

        Returns:
            ValidationResult with detailed error information if invalid.
        """
        if command is None:
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot be None",
                error_code=ValidationErrorCode.EMPTY_COMMAND,
                suggestion="Provide a valid shell command string",
            )

        if not command or command.isspace():
            return ValidationResult(
                is_valid=False,
                error_message="Command is empty or contains only whitespace",
                error_code=ValidationErrorCode.EMPTY_COMMAND,
                suggestion="Provide a non-empty shell command",
            )

        # Run all validation checks
        checks = [
            self._check_quotes_detailed,
            self._check_trailing_operators,
            self._check_leading_operators,
            self._check_balanced_delimiters_detailed,
            self._check_pipe_chain_integrity,
            self._check_logical_operator_chains,
            self._check_redirections_detailed,
            self._check_command_structure_detailed,
            self._check_control_flow_keywords,
        ]

        for check in checks:
            result = check(command)
            if not result.is_valid:
                return result

        return ValidationResult(is_valid=True)

    def _check_quotes_detailed(self, command: str) -> ValidationResult:
        """Check for unclosed quotes with detailed position information."""
        single_quote_start: Optional[int] = None
        double_quote_start: Optional[int] = None
        backtick_start: Optional[int] = None
        escaped = False

        for i, char in enumerate(command):
            if escaped:
                escaped = False
                continue

            if char == "\\":
                if double_quote_start is not None or (
                    single_quote_start is None and backtick_start is None
                ):
                    escaped = True
                continue

            if char == "'" and double_quote_start is None and backtick_start is None:
                if single_quote_start is None:
                    single_quote_start = i
                else:
                    single_quote_start = None
                continue

            if char == '"' and single_quote_start is None and backtick_start is None:
                if double_quote_start is None:
                    double_quote_start = i
                else:
                    double_quote_start = None
                continue

            if char == "`" and single_quote_start is None:
                if backtick_start is None:
                    backtick_start = i
                else:
                    backtick_start = None
                continue

        if single_quote_start is not None:
            context = self._get_context_snippet(command, single_quote_start)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed single quote starting at position {single_quote_start}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_SINGLE_QUOTE,
                error_position=single_quote_start,
                suggestion="Add a closing single quote (') to match the opening quote",
            )

        if double_quote_start is not None:
            context = self._get_context_snippet(command, double_quote_start)
            return ValidationResult(
                is_valid=False,
                error_message=f'Unclosed double quote starting at position {double_quote_start}: {context}',
                error_code=ValidationErrorCode.UNCLOSED_DOUBLE_QUOTE,
                error_position=double_quote_start,
                suggestion='Add a closing double quote (") to match the opening quote',
            )

        if backtick_start is not None:
            context = self._get_context_snippet(command, backtick_start)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed backtick starting at position {backtick_start}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_BACKTICK,
                error_position=backtick_start,
                suggestion="Add a closing backtick (`) or use $(...) for command substitution instead",
            )

        try:
            shlex.split(command)
        except ValueError as e:
            error_msg = str(e)
            return ValidationResult(
                is_valid=False,
                error_message=f"Shell parsing error: {error_msg}",
                error_code=ValidationErrorCode.PARSE_ERROR,
                suggestion="Check for unclosed quotes or escape sequences",
            )

        return ValidationResult(is_valid=True)

    def _check_trailing_operators(self, command: str) -> ValidationResult:
        """Check for incomplete trailing operators."""
        stripped = command.rstrip()
        if not stripped:
            return ValidationResult(is_valid=True)

        if stripped.endswith("|") and not stripped.endswith("||"):
            return ValidationResult(
                is_valid=False,
                error_message="Command ends with incomplete pipe operator '|'",
                error_code=ValidationErrorCode.TRAILING_PIPE,
                error_position=len(stripped) - 1,
                suggestion="Add a command after the pipe, e.g., 'cmd1 | cmd2'",
            )

        if stripped.endswith("&&"):
            return ValidationResult(
                is_valid=False,
                error_message="Command ends with incomplete AND operator '&&'",
                error_code=ValidationErrorCode.TRAILING_AND,
                error_position=len(stripped) - 2,
                suggestion="Add a command after &&, e.g., 'cmd1 && cmd2'",
            )

        if stripped.endswith("||"):
            return ValidationResult(
                is_valid=False,
                error_message="Command ends with incomplete OR operator '||'",
                error_code=ValidationErrorCode.TRAILING_OR,
                error_position=len(stripped) - 2,
                suggestion="Add a command after ||, e.g., 'cmd1 || cmd2'",
            )

        if stripped.endswith("&") and not stripped.endswith("&&"):
            if len(stripped) >= 2 and stripped[-2] in "<>":
                return ValidationResult(
                    is_valid=False,
                    error_message="Redirection operator missing target file",
                    error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                    error_position=len(stripped) - 1,
                    suggestion="Specify a file after the redirection, e.g., 'cmd &> file'",
                )

        # Use pre-compiled pattern
        redirect_match = self._patterns.TRAILING_REDIRECT.search(stripped)
        if redirect_match:
            op = redirect_match.group().strip()
            return ValidationResult(
                is_valid=False,
                error_message=f"Redirection operator '{op}' missing target file",
                error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                error_position=redirect_match.start(),
                suggestion=f"Specify a file after '{op}', e.g., 'cmd {op} filename'",
            )

        if stripped.endswith(";"):
            if stripped == ";":
                return ValidationResult(
                    is_valid=False,
                    error_message="Command contains only a semicolon",
                    error_code=ValidationErrorCode.TRAILING_SEMICOLON,
                    error_position=0,
                    suggestion="Provide a command before the semicolon",
                )

        if stripped.endswith("\\"):
            return ValidationResult(
                is_valid=False,
                error_message="Command ends with line continuation backslash but no following line",
                error_code=ValidationErrorCode.TRAILING_BACKSLASH,
                error_position=len(stripped) - 1,
                suggestion="Remove the trailing backslash or add the continued command",
            )

        return ValidationResult(is_valid=True)

    def _check_leading_operators(self, command: str) -> ValidationResult:
        """Check for invalid leading operators."""
        stripped = command.lstrip()
        if not stripped:
            return ValidationResult(is_valid=True)

        if stripped.startswith("|") and not stripped.startswith("||"):
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot start with pipe operator '|'",
                error_code=ValidationErrorCode.LEADING_PIPE,
                error_position=command.index("|"),
                suggestion="Pipes connect commands; add a command before '|', e.g., 'cmd1 | cmd2'",
            )

        if stripped.startswith("&&"):
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot start with AND operator '&&'",
                error_code=ValidationErrorCode.LEADING_AND,
                error_position=command.index("&"),
                suggestion="'&&' chains commands; add a command before it, e.g., 'cmd1 && cmd2'",
            )

        if stripped.startswith("||"):
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot start with OR operator '||'",
                error_code=ValidationErrorCode.LEADING_OR,
                error_position=command.index("|"),
                suggestion="'||' provides fallback; add a command before it, e.g., 'cmd1 || cmd2'",
            )

        if stripped.startswith(";"):
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot start with semicolon ';'",
                error_code=ValidationErrorCode.LEADING_SEMICOLON,
                error_position=command.index(";"),
                suggestion="Remove the leading semicolon or add a command before it",
            )

        return ValidationResult(is_valid=True)

    def _check_balanced_delimiters_detailed(self, command: str) -> ValidationResult:
        """Check for balanced delimiters with detailed position tracking."""
        paren_stack: list[int] = []
        brace_stack: list[int] = []
        bracket_stack: list[int] = []
        subshell_stack: list[int] = []

        in_single_quote = False
        in_double_quote = False
        escaped = False
        i = 0

        words = self._extract_unquoted_words(command)
        has_case = "case" in words and "in" in words

        while i < len(command):
            char = command[i]

            if escaped:
                escaped = False
                i += 1
                continue

            if char == "\\" and not in_single_quote:
                escaped = True
                i += 1
                continue

            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                i += 1
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                i += 1
                continue

            if in_single_quote or in_double_quote:
                i += 1
                continue

            if char == "$" and i + 1 < len(command) and command[i + 1] == "(":
                subshell_stack.append(i)
                i += 2
                continue

            if char == "(":
                paren_stack.append(i)
            elif char == ")":
                if subshell_stack and (not paren_stack or subshell_stack[-1] > paren_stack[-1]):
                    subshell_stack.pop()
                elif paren_stack:
                    paren_stack.pop()
                elif has_case:
                    pass
                else:
                    context = self._get_context_snippet(command, i)
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Unmatched closing parenthesis ')' at position {i}: {context}",
                        error_code=ValidationErrorCode.UNMATCHED_PARENTHESIS,
                        error_position=i,
                        suggestion="Remove the extra ')' or add a matching '(' earlier in the command",
                    )
            elif char == "{":
                brace_stack.append(i)
            elif char == "}":
                if brace_stack:
                    brace_stack.pop()
                else:
                    context = self._get_context_snippet(command, i)
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Unmatched closing brace '}}' at position {i}: {context}",
                        error_code=ValidationErrorCode.UNMATCHED_BRACE,
                        error_position=i,
                        suggestion="Remove the extra '}}' or add a matching '{{' earlier in the command",
                    )
            elif char == "[":
                bracket_stack.append(i)
            elif char == "]":
                if bracket_stack:
                    bracket_stack.pop()
                else:
                    context = self._get_context_snippet(command, i)
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Unmatched closing bracket ']' at position {i}: {context}",
                        error_code=ValidationErrorCode.UNMATCHED_BRACKET,
                        error_position=i,
                        suggestion="Remove the extra ']' or add a matching '[' earlier in the command",
                    )

            i += 1

        if subshell_stack:
            pos = subshell_stack[0]
            context = self._get_context_snippet(command, pos)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed command substitution '$(' starting at position {pos}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_COMMAND_SUBSTITUTION,
                error_position=pos,
                suggestion="Add a closing ')' to complete the $(...) command substitution",
            )

        if paren_stack:
            pos = paren_stack[0]
            context = self._get_context_snippet(command, pos)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed parenthesis '(' starting at position {pos}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_PARENTHESIS,
                error_position=pos,
                suggestion="Add a closing ')' to match the opening '('",
            )

        if brace_stack:
            pos = brace_stack[0]
            context = self._get_context_snippet(command, pos)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed brace '{{' starting at position {pos}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_BRACE,
                error_position=pos,
                suggestion="Add a closing '}}' to match the opening '{{'",
            )

        if bracket_stack:
            pos = bracket_stack[0]
            context = self._get_context_snippet(command, pos)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed bracket '[' starting at position {pos}: {context}",
                error_code=ValidationErrorCode.UNCLOSED_BRACKET,
                error_position=pos,
                suggestion="Add a closing ']' to match the opening '['",
            )

        return ValidationResult(is_valid=True)

    def _check_pipe_chain_integrity(self, command: str) -> ValidationResult:
        """Check for valid pipe chain structure."""
        segments = self._split_by_operator(command, "|", exclude_double=True)

        for i, segment in enumerate(segments):
            stripped = segment.strip()
            if not stripped:
                if i == 0 or i == len(segments) - 1:
                    continue
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Empty command in pipe chain at segment {i + 1}",
                    error_code=ValidationErrorCode.EMPTY_PIPE_SEGMENT,
                    suggestion="Each segment in a pipe chain must contain a command, e.g., 'cmd1 | cmd2 | cmd3'",
                )

        return ValidationResult(is_valid=True)

    def _check_logical_operator_chains(self, command: str) -> ValidationResult:
        """Check for valid logical operator (&&, ||) chain structure."""
        and_segments = self._split_by_operator(command, "&&")
        for i, segment in enumerate(and_segments):
            stripped = segment.strip()
            if not stripped and 0 < i < len(and_segments) - 1:
                return ValidationResult(
                    is_valid=False,
                    error_message="Empty command between '&&' operators",
                    error_code=ValidationErrorCode.EMPTY_AND_SEGMENT,
                    suggestion="Add a command between the '&&' operators, e.g., 'cmd1 && cmd2 && cmd3'",
                )

        or_segments = self._split_by_operator(command, "||")
        for i, segment in enumerate(or_segments):
            stripped = segment.strip()
            if not stripped and 0 < i < len(or_segments) - 1:
                return ValidationResult(
                    is_valid=False,
                    error_message="Empty command between '||' operators",
                    error_code=ValidationErrorCode.EMPTY_OR_SEGMENT,
                    suggestion="Add a command between the '||' operators, e.g., 'cmd1 || cmd2 || cmd3'",
                )

        return ValidationResult(is_valid=True)

    def _check_redirections_detailed(self, command: str) -> ValidationResult:
        """Check for malformed redirections with detailed messages."""
        # Use pre-compiled patterns
        match = self._patterns.INVALID_INPUT_REDIRECT.search(command)
        if match:
            return ValidationResult(
                is_valid=False,
                error_message="Invalid redirection '< <' - did you mean '<<' (here-doc) or '<<<' (here-string)?",
                error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                error_position=match.start(),
                suggestion="Use '<<' for here-documents or '<<<' for here-strings",
            )

        match = self._patterns.INVALID_OUTPUT_REDIRECT.search(command)
        if match:
            return ValidationResult(
                is_valid=False,
                error_message="Invalid redirection '> >' - did you mean '>>' (append)?",
                error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                error_position=match.start(),
                suggestion="Use '>>' without space for append redirection",
            )

        return ValidationResult(is_valid=True)

    def _check_command_structure_detailed(self, command: str) -> ValidationResult:
        """Check for malformed command structures."""
        words = self._extract_unquoted_words(command)
        has_case = "case" in words

        if not has_case:
            match = self._patterns.CONSECUTIVE_SEMICOLONS.search(command)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Multiple consecutive semicolons at position {match.start()}",
                    error_code=ValidationErrorCode.CONSECUTIVE_SEMICOLONS,
                    error_position=match.start(),
                    suggestion="Remove extra semicolons; use single ';' to separate commands",
                )
        else:
            match = self._patterns.TRIPLE_SEMICOLONS.search(command)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Too many consecutive semicolons at position {match.start()}",
                    error_code=ValidationErrorCode.CONSECUTIVE_SEMICOLONS,
                    error_position=match.start(),
                    suggestion="Use ';;' to end case patterns, not more semicolons",
                )

        if self._patterns.INVALID_VAR_ASSIGNMENT.match(command):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid variable assignment - missing variable name before '='",
                error_code=ValidationErrorCode.INVALID_VARIABLE_ASSIGNMENT,
                error_position=command.index("="),
                suggestion="Variable assignment requires a name, e.g., 'VAR=value'",
            )

        return ValidationResult(is_valid=True)

    def _check_control_flow_keywords(self, command: str) -> ValidationResult:
        """Check for balanced shell control flow keywords (if/fi, for/done, etc.)."""
        words = self._extract_unquoted_words(command)

        if_count = 0
        for_count = 0
        while_count = 0
        until_count = 0
        case_count = 0
        select_count = 0

        for word in words:
            if word == "if":
                if_count += 1
            elif word == "fi":
                if_count -= 1
                if if_count < 0:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Unmatched 'fi' - missing corresponding 'if'",
                        error_code=ValidationErrorCode.UNMATCHED_IF_THEN_FI,
                        suggestion="Add an 'if' statement before 'fi', or remove the extra 'fi'",
                    )
            elif word == "for":
                for_count += 1
            elif word == "while":
                while_count += 1
            elif word == "until":
                until_count += 1
            elif word == "select":
                select_count += 1
            elif word == "done":
                if for_count > 0:
                    for_count -= 1
                elif while_count > 0:
                    while_count -= 1
                elif until_count > 0:
                    until_count -= 1
                elif select_count > 0:
                    select_count -= 1
                else:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Unmatched 'done' - missing corresponding 'for', 'while', 'until', or 'select'",
                        error_code=ValidationErrorCode.UNMATCHED_FOR_DO_DONE,
                        suggestion="Add a loop statement before 'done', or remove the extra 'done'",
                    )
            elif word == "case":
                case_count += 1
            elif word == "esac":
                case_count -= 1
                if case_count < 0:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Unmatched 'esac' - missing corresponding 'case'",
                        error_code=ValidationErrorCode.UNMATCHED_CASE_ESAC,
                        suggestion="Add a 'case' statement before 'esac', or remove the extra 'esac'",
                    )

        if if_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'if' statement - missing 'fi' ({if_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_IF_THEN_FI,
                suggestion="Add 'fi' to close the 'if' statement: if condition; then commands; fi",
            )

        if for_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'for' loop - missing 'done' ({for_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_FOR_DO_DONE,
                suggestion="Add 'done' to close the 'for' loop: for var in list; do commands; done",
            )

        if while_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'while' loop - missing 'done' ({while_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_WHILE_DO_DONE,
                suggestion="Add 'done' to close the 'while' loop: while condition; do commands; done",
            )

        if until_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'until' loop - missing 'done' ({until_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_WHILE_DO_DONE,
                suggestion="Add 'done' to close the 'until' loop: until condition; do commands; done",
            )

        if select_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'select' statement - missing 'done' ({select_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_FOR_DO_DONE,
                suggestion="Add 'done' to close the 'select' statement: select var in list; do commands; done",
            )

        if case_count > 0:
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed 'case' statement - missing 'esac' ({case_count} unclosed)",
                error_code=ValidationErrorCode.UNMATCHED_CASE_ESAC,
                suggestion="Add 'esac' to close the 'case' statement: case $var in pattern) commands;; esac",
            )

        return ValidationResult(is_valid=True)

    def _split_by_operator(
        self, command: str, operator: str, exclude_double: bool = False
    ) -> list[str]:
        """Split command by operator, respecting quotes and subshells."""
        segments = []
        current: list[str] = []
        in_single_quote = False
        in_double_quote = False
        paren_depth = 0
        escaped = False
        i = 0
        cmd_len = len(command)
        op_len = len(operator)

        while i < cmd_len:
            char = command[i]

            if escaped:
                current.append(char)
                escaped = False
                i += 1
                continue

            if char == "\\" and not in_single_quote:
                current.append(char)
                escaped = True
                i += 1
                continue

            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current.append(char)
                i += 1
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current.append(char)
                i += 1
                continue

            if not in_single_quote and not in_double_quote:
                if char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth -= 1

                if paren_depth == 0 and command[i:i + op_len] == operator:
                    if exclude_double and op_len == 1:
                        if i + 1 < cmd_len and command[i + 1] == operator:
                            current.append(char)
                            i += 1
                            continue

                    segments.append("".join(current))
                    current = []
                    i += op_len
                    continue

            current.append(char)
            i += 1

        segments.append("".join(current))
        return segments

    def _extract_unquoted_words(self, command: str) -> list[str]:
        """Extract words from command that are not inside quotes."""
        words = []
        current_word: list[str] = []
        in_single_quote = False
        in_double_quote = False
        escaped = False

        for char in command:
            if escaped:
                escaped = False
                if not in_single_quote and not in_double_quote:
                    current_word.append(char)
                continue

            if char == "\\" and not in_single_quote:
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

            if char.isspace() or char in ";|&<>(){}":
                if current_word:
                    words.append("".join(current_word))
                    current_word = []
            else:
                current_word.append(char)

        if current_word:
            words.append("".join(current_word))

        return words

    def _get_context_snippet(self, command: str, position: int, context_size: int = 20) -> str:
        """Get a snippet of the command around the error position."""
        start = max(0, position - context_size // 2)
        end = min(len(command), position + context_size // 2)

        snippet = command[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(command):
            snippet = snippet + "..."

        return f"'{snippet}'"


# Singleton instance for convenience
_validator = CommandValidator()


def validate_command(command: str) -> ValidationResult:
    """
    Validate a shell command for syntax errors and malformed constructs.

    Args:
        command: The shell command string to validate.

    Returns:
        ValidationResult with detailed error information if invalid.
    """
    return _validator.validate(command)


def print_validation_error(
    result: ValidationResult,
    command: Optional[str] = None,
    console: Optional[Console] = None,
    use_panel: bool = False,
) -> None:
    """
    Print a validation error with Rich styling.

    Args:
        result: The validation result to print.
        command: Optional command string for context.
        console: Optional Rich console instance.
        use_panel: If True, display error in a panel.
    """
    if console is None:
        console = Console()

    if result.is_valid:
        return

    if use_panel:
        console.print(result.to_panel(command))
    else:
        result.print_styled(console)
