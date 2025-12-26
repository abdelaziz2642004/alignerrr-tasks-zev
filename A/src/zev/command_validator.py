"""Command validation module for checking shell command syntax and safety."""

import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ValidationErrorType(Enum):
    """Types of validation errors for categorization."""

    EMPTY_COMMAND = "empty_command"
    UNCLOSED_QUOTE = "unclosed_quote"
    UNBALANCED_DELIMITER = "unbalanced_delimiter"
    INVALID_PIPE = "invalid_pipe"
    INVALID_REDIRECT = "invalid_redirect"
    INVALID_OPERATOR = "invalid_operator"
    INCOMPLETE_CONTROL_STRUCTURE = "incomplete_control_structure"
    INVALID_SYNTAX = "invalid_syntax"
    INVALID_SUBSTITUTION = "invalid_substitution"


@dataclass
class ValidationResult:
    """Result of command validation with detailed error information."""

    is_valid: bool
    error_message: Optional[str] = None
    error_type: Optional[ValidationErrorType] = None
    position: Optional[int] = None  # Character position where error was detected
    suggestion: Optional[str] = None  # Suggested fix for the error

    def __str__(self) -> str:
        if self.is_valid:
            return "Valid command"
        parts = [self.error_message or "Unknown error"]
        if self.position is not None:
            parts.append(f"(at position {self.position})")
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " ".join(parts)


@dataclass
class QuoteState:
    """Tracks the state of quotes while parsing a command."""

    in_single_quote: bool = False
    in_double_quote: bool = False
    in_backtick: bool = False
    single_quote_start: int = -1
    double_quote_start: int = -1
    backtick_start: int = -1

    @property
    def in_any_quote(self) -> bool:
        return self.in_single_quote or self.in_double_quote or self.in_backtick


@dataclass
class DelimiterStack:
    """Tracks nested delimiters with positions."""

    stack: list = field(default_factory=list)

    def push(self, char: str, position: int) -> None:
        self.stack.append((char, position))

    def pop(self, expected_open: str) -> Optional[tuple]:
        if self.stack and self.stack[-1][0] == expected_open:
            return self.stack.pop()
        return None

    def peek(self) -> Optional[tuple]:
        return self.stack[-1] if self.stack else None

    @property
    def is_empty(self) -> bool:
        return len(self.stack) == 0


class CommandValidator:
    """Validates shell commands for syntax errors and malformed constructs."""

    # Shell control structure keywords
    CONTROL_KEYWORDS_OPEN = {"if", "for", "while", "until", "case", "select"}
    CONTROL_KEYWORDS_CLOSE = {"fi", "done", "esac"}
    CONTROL_KEYWORD_PAIRS = {
        "if": "fi",
        "for": "done",
        "while": "done",
        "until": "done",
        "case": "esac",
        "select": "done",
    }

    # Delimiter pairs
    DELIMITER_PAIRS = {
        "(": ")",
        "{": "}",
        "[": "]",
        "$(": ")",
        "${": "}",
    }
    OPEN_DELIMITERS = {"(", "{", "["}
    CLOSE_DELIMITERS = {")", "}", "]"}
    DELIMITER_NAMES = {
        "(": "parenthesis",
        ")": "parenthesis",
        "{": "brace",
        "}": "brace",
        "[": "bracket",
        "]": "bracket",
    }

    def validate(self, command: str) -> ValidationResult:
        """
        Validate a shell command for syntax errors and malformed constructs.

        Performs comprehensive validation including:
        - Empty command detection
        - Quote balancing (single, double, backticks)
        - Delimiter balancing (parentheses, braces, brackets)
        - Pipe and operator validation
        - Redirection syntax checking
        - Control structure validation
        - Command substitution validation

        Args:
            command: The shell command string to validate.

        Returns:
            ValidationResult with detailed error information if invalid.
        """
        if command is None:
            return ValidationResult(
                is_valid=False,
                error_message="Command cannot be None",
                error_type=ValidationErrorType.EMPTY_COMMAND,
                suggestion="Provide a valid command string",
            )

        # Check for empty command
        if not command or command.isspace():
            return ValidationResult(
                is_valid=False,
                error_message="Command is empty or contains only whitespace",
                error_type=ValidationErrorType.EMPTY_COMMAND,
                suggestion="Provide a non-empty command",
            )

        # Run all validation checks
        checks = [
            self._check_quotes,
            self._check_delimiters,
            self._check_operators,
            self._check_pipes,
            self._check_redirections,
            self._check_control_structures,
            self._check_command_substitution,
            self._check_general_syntax,
        ]

        for check in checks:
            result = check(command)
            if not result.is_valid:
                return result

        return ValidationResult(is_valid=True)

    def _check_quotes(self, command: str) -> ValidationResult:
        """
        Check for properly balanced and closed quotes.

        Handles:
        - Single quotes (')
        - Double quotes (")
        - Backticks (`)
        - Escaped characters within quotes
        """
        state = QuoteState()
        i = 0

        while i < len(command):
            char = command[i]

            # Handle escape sequences (only in double quotes or unquoted)
            if char == "\\" and not state.in_single_quote:
                # Skip the next character
                i += 2
                continue

            # Single quote handling
            if char == "'" and not state.in_double_quote and not state.in_backtick:
                if state.in_single_quote:
                    state.in_single_quote = False
                    state.single_quote_start = -1
                else:
                    state.in_single_quote = True
                    state.single_quote_start = i

            # Double quote handling
            elif char == '"' and not state.in_single_quote and not state.in_backtick:
                if state.in_double_quote:
                    state.in_double_quote = False
                    state.double_quote_start = -1
                else:
                    state.in_double_quote = True
                    state.double_quote_start = i

            # Backtick handling
            elif char == "`" and not state.in_single_quote:
                if state.in_backtick:
                    state.in_backtick = False
                    state.backtick_start = -1
                else:
                    state.in_backtick = True
                    state.backtick_start = i

            i += 1

        # Check for unclosed quotes
        if state.in_single_quote:
            context = self._get_context_around(command, state.single_quote_start)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed single quote starting at position {state.single_quote_start}: {context}",
                error_type=ValidationErrorType.UNCLOSED_QUOTE,
                position=state.single_quote_start,
                suggestion="Add a closing single quote (') to match the opening quote",
            )

        if state.in_double_quote:
            context = self._get_context_around(command, state.double_quote_start)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed double quote starting at position {state.double_quote_start}: {context}",
                error_type=ValidationErrorType.UNCLOSED_QUOTE,
                position=state.double_quote_start,
                suggestion='Add a closing double quote (") to match the opening quote',
            )

        if state.in_backtick:
            context = self._get_context_around(command, state.backtick_start)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed backtick starting at position {state.backtick_start}: {context}",
                error_type=ValidationErrorType.UNCLOSED_QUOTE,
                position=state.backtick_start,
                suggestion="Add a closing backtick (`) or consider using $() for command substitution instead",
            )

        return ValidationResult(is_valid=True)

    def _check_delimiters(self, command: str) -> ValidationResult:
        """
        Check for balanced parentheses, braces, and brackets.

        Properly handles delimiters inside quotes and case statement patterns.
        """
        stack = DelimiterStack()
        state = QuoteState()
        in_case = False
        i = 0

        while i < len(command):
            char = command[i]

            # Update quote state
            if char == "\\" and not state.in_single_quote:
                i += 2
                continue

            if char == "'" and not state.in_double_quote and not state.in_backtick:
                state.in_single_quote = not state.in_single_quote
            elif char == '"' and not state.in_single_quote and not state.in_backtick:
                state.in_double_quote = not state.in_double_quote
            elif char == "`" and not state.in_single_quote:
                state.in_backtick = not state.in_backtick

            # Track if we're in a case statement
            if not state.in_any_quote:
                # Check for 'case' keyword
                if command[i:i+4] == "case" and (i == 0 or not command[i-1].isalnum()):
                    if i + 4 >= len(command) or not command[i+4].isalnum():
                        in_case = True
                # Check for 'esac' keyword
                if command[i:i+4] == "esac" and (i == 0 or not command[i-1].isalnum()):
                    if i + 4 >= len(command) or not command[i+4].isalnum():
                        in_case = False

            # Only check delimiters outside quotes
            if not state.in_any_quote:
                # Check for $( and ${ constructs
                if char == "$" and i + 1 < len(command):
                    next_char = command[i + 1]
                    if next_char == "(":
                        stack.push("$(", i)
                        i += 2
                        continue
                    elif next_char == "{":
                        stack.push("${", i)
                        i += 2
                        continue

                if char in self.OPEN_DELIMITERS:
                    stack.push(char, i)
                elif char in self.CLOSE_DELIMITERS:
                    expected_open = {")" : "(", "}" : "{", "]" : "["}[char]

                    # Check for $( or ${ closures
                    top = stack.peek()
                    if top and top[0] in ("$(", "${"):
                        expected_close = ")" if top[0] == "$(" else "}"
                        if char == expected_close:
                            stack.pop(top[0])
                            i += 1
                            continue

                    # In case statements, ) is used as pattern delimiter, not grouping
                    if char == ")" and in_case:
                        # Check if this looks like a case pattern (preceded by pattern chars)
                        # Case patterns end with ) but don't have matching (
                        if stack.is_empty or stack.peek()[0] != "(":
                            i += 1
                            continue

                    popped = stack.pop(expected_open)
                    if popped is None:
                        delimiter_name = self.DELIMITER_NAMES.get(char, "delimiter")
                        return ValidationResult(
                            is_valid=False,
                            error_message=f"Unmatched closing {delimiter_name} '{char}' at position {i}",
                            error_type=ValidationErrorType.UNBALANCED_DELIMITER,
                            position=i,
                            suggestion=f"Remove the extra '{char}' or add a matching opening '{expected_open}'",
                        )

            i += 1

        # Check for unclosed delimiters
        if not stack.is_empty:
            unclosed = stack.peek()
            delimiter_name = self.DELIMITER_NAMES.get(unclosed[0], "delimiter")
            if unclosed[0] in ("$(", "${"):
                delimiter_name = "command substitution" if unclosed[0] == "$(" else "variable expansion"
            expected_close = self.DELIMITER_PAIRS.get(unclosed[0], ")")
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed {delimiter_name} '{unclosed[0]}' starting at position {unclosed[1]}",
                error_type=ValidationErrorType.UNBALANCED_DELIMITER,
                position=unclosed[1],
                suggestion=f"Add a closing '{expected_close}' to match the opening '{unclosed[0]}'",
            )

        return ValidationResult(is_valid=True)

    def _check_operators(self, command: str) -> ValidationResult:
        """
        Check for valid usage of shell operators.

        Validates:
        - Commands don't start with operators (|, &, &&, ||)
        - Commands don't end with incomplete operators
        - No invalid operator combinations
        """
        stripped = command.strip()

        # Check for invalid starting operators
        invalid_starts = [
            (r"^\|(?!\|)", "pipe (|)", "A pipe requires a command before it to provide input"),
            (r"^&&", "logical AND (&&)", "The && operator requires a command before it"),
            (r"^\|\|", "logical OR (||)", "The || operator requires a command before it"),
            (r"^&(?!&)", "background operator (&)", "The & operator must come after a command"),
            (r"^;", "semicolon (;)", "A semicolon is used to separate commands, not start them"),
        ]

        for pattern, name, explanation in invalid_starts:
            if re.match(pattern, stripped):
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Command cannot start with {name}. {explanation}",
                    error_type=ValidationErrorType.INVALID_OPERATOR,
                    position=0,
                    suggestion=f"Remove the leading '{name.split()[0]}' or add a command before it",
                )

        # Check for incomplete trailing operators
        incomplete_ends = [
            (r"\|\s*$", "pipe (|)", "Add a command after the pipe to receive the output"),
            (r"&&\s*$", "logical AND (&&)", "Add a command after && that should run if the first succeeds"),
            (r"\|\|\s*$", "logical OR (||)", "Add a command after || that should run if the first fails"),
            (r"(?<![>])[>]\s*$", "output redirection (>)", "Specify a file path after > to redirect output"),
            (r"[<]\s*$", "input redirection (<)", "Specify a file path after < to redirect input"),
        ]

        for pattern, name, explanation in incomplete_ends:
            match = re.search(pattern, stripped)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Command ends with incomplete {name}. {explanation}",
                    error_type=ValidationErrorType.INVALID_OPERATOR,
                    position=len(command) - len(command.rstrip()),
                    suggestion=explanation,
                )

        # Check for invalid operator combinations
        # Note: ;; is valid in case statements, so we need to check context
        unquoted = self._remove_quoted_content(command)
        in_case_statement = bool(re.search(r"\bcase\b.*\bin\b", unquoted))

        invalid_combos = [
            (r";\s*;", "double semicolons (;;)", "Remove one semicolon or add a command between them", not in_case_statement),
            (r"&\s*&\s*&", "triple ampersands (&&&)", "Use && for logical AND or & for background execution", True),
            (r"\|\s*\|\s*\|", "triple pipes (|||)", "Use || for logical OR or | for piping", True),
        ]

        for pattern, name, suggestion, should_check in invalid_combos:
            if not should_check:
                continue
            match = re.search(pattern, stripped)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Invalid operator sequence: {name}",
                    error_type=ValidationErrorType.INVALID_OPERATOR,
                    position=match.start(),
                    suggestion=suggestion,
                )

        return ValidationResult(is_valid=True)

    def _check_pipes(self, command: str) -> ValidationResult:
        """
        Check for valid pipe usage.

        Validates:
        - Each pipe segment has a command
        - No empty segments between pipes
        """
        # Remove quoted content to avoid false positives
        unquoted = self._remove_quoted_content(command)

        # Split by single pipe (not ||)
        # Use negative lookbehind and lookahead to avoid ||
        segments = re.split(r"(?<!\|)\|(?!\|)", unquoted)

        for i, segment in enumerate(segments):
            stripped = segment.strip()

            # Check for empty segments (but allow if it's the result of || being split weirdly)
            if not stripped and len(segments) > 1:
                if i == 0:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Empty command before pipe. Each pipe segment must have a command",
                        error_type=ValidationErrorType.INVALID_PIPE,
                        position=0,
                        suggestion="Add a command before the pipe that produces output",
                    )
                elif i == len(segments) - 1:
                    return ValidationResult(
                        is_valid=False,
                        error_message="Empty command after pipe. Each pipe segment must have a command",
                        error_type=ValidationErrorType.INVALID_PIPE,
                        suggestion="Add a command after the pipe to process the input",
                    )
                else:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Empty pipe segment at position {i + 1}. Each pipe segment must have a command",
                        error_type=ValidationErrorType.INVALID_PIPE,
                        suggestion="Add a command in the empty segment or remove the extra pipe",
                    )

        return ValidationResult(is_valid=True)

    def _check_redirections(self, command: str) -> ValidationResult:
        """
        Check for valid redirection syntax.

        Validates:
        - Redirections have proper targets
        - File descriptors are valid
        - No conflicting redirections
        """
        unquoted = self._remove_quoted_content(command)

        # Check for redirection without target (more specific patterns)
        # Pattern: > or >> at end of string or followed by another operator
        redirect_issues = [
            (r">\s*>(?!>)", "Malformed output redirection: space between > characters. Use >> for append", "Use >> (no space) to append to a file"),
            (r"<\s*<(?!<)", "Malformed input redirection: space between < characters. Use << for here-doc", "Use << (no space) for here-documents"),
            (r">\s*\|", "Invalid redirection: > followed by pipe. Output is already redirected", "Remove the > if you want to pipe, or remove | if you want to redirect to file"),
            (r"[0-9]+<>\s*$", "Incomplete read-write redirection: missing filename", "Specify a filename after the <> operator"),
        ]

        for pattern, message, suggestion in redirect_issues:
            match = re.search(pattern, unquoted)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=message,
                    error_type=ValidationErrorType.INVALID_REDIRECT,
                    position=match.start(),
                    suggestion=suggestion,
                )

        # Check for invalid file descriptor numbers (only 0-9 are standard)
        fd_pattern = r"([0-9]{2,})[<>]"
        match = re.search(fd_pattern, unquoted)
        if match:
            fd = match.group(1)
            return ValidationResult(
                is_valid=False,
                error_message=f"Unusual file descriptor number: {fd}. Standard descriptors are 0 (stdin), 1 (stdout), 2 (stderr)",
                error_type=ValidationErrorType.INVALID_REDIRECT,
                position=match.start(),
                suggestion="Use file descriptors 0-9, typically 0, 1, or 2",
            )

        return ValidationResult(is_valid=True)

    def _check_control_structures(self, command: str) -> ValidationResult:
        """
        Check for balanced shell control structures.

        Validates if/then/fi, for/do/done, while/do/done, case/esac, etc.
        """
        unquoted = self._remove_quoted_content(command)

        # Extract words to find control keywords
        # This is a simplified check - full validation would require parsing
        words = re.findall(r"\b(\w+)\b", unquoted)

        # Track control structure nesting
        control_stack = []

        for word in words:
            if word in self.CONTROL_KEYWORDS_OPEN:
                control_stack.append(word)
            elif word in self.CONTROL_KEYWORDS_CLOSE:
                if not control_stack:
                    opener = [k for k, v in self.CONTROL_KEYWORD_PAIRS.items() if v == word]
                    opener_str = opener[0] if opener else "unknown"
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Unexpected '{word}' without matching '{opener_str}'",
                        error_type=ValidationErrorType.INCOMPLETE_CONTROL_STRUCTURE,
                        suggestion=f"Add '{opener_str}' before '{word}' or remove the '{word}'",
                    )

                expected_close = self.CONTROL_KEYWORD_PAIRS.get(control_stack[-1])
                if expected_close == word:
                    control_stack.pop()
                else:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Mismatched control structure: expected '{expected_close}' but found '{word}'",
                        error_type=ValidationErrorType.INCOMPLETE_CONTROL_STRUCTURE,
                        suggestion=f"Replace '{word}' with '{expected_close}' or check your control structure nesting",
                    )

        # Check for unclosed control structures
        if control_stack:
            unclosed = control_stack[-1]
            expected = self.CONTROL_KEYWORD_PAIRS.get(unclosed, "unknown")
            return ValidationResult(
                is_valid=False,
                error_message=f"Unclosed '{unclosed}' statement - missing '{expected}'",
                error_type=ValidationErrorType.INCOMPLETE_CONTROL_STRUCTURE,
                suggestion=f"Add '{expected}' to close the '{unclosed}' statement",
            )

        return ValidationResult(is_valid=True)

    def _check_command_substitution(self, command: str) -> ValidationResult:
        """
        Check for valid command substitution syntax.

        Validates $() and backtick substitutions.
        """
        # Check for incomplete $( without closing )
        # This is partially handled by delimiter checking, but we add specific messages

        # Check for $( followed immediately by )
        if re.search(r"\$\(\s*\)", command):
            match = re.search(r"\$\(\s*\)", command)
            return ValidationResult(
                is_valid=False,
                error_message="Empty command substitution $() - no command inside",
                error_type=ValidationErrorType.INVALID_SUBSTITUTION,
                position=match.start() if match else None,
                suggestion="Add a command inside $() or remove the empty substitution",
            )

        # Check for empty backticks
        if re.search(r"`\s*`", command):
            match = re.search(r"`\s*`", command)
            return ValidationResult(
                is_valid=False,
                error_message="Empty backtick substitution `` - no command inside",
                error_type=ValidationErrorType.INVALID_SUBSTITUTION,
                position=match.start() if match else None,
                suggestion="Add a command inside backticks or use $() syntax instead",
            )

        # Check for nested backticks (which don't work - should use $())
        backtick_count = command.count("`")
        if backtick_count > 2:
            return ValidationResult(
                is_valid=False,
                error_message="Multiple backticks detected - nested command substitution with backticks is error-prone",
                error_type=ValidationErrorType.INVALID_SUBSTITUTION,
                suggestion="Use $() syntax for command substitution, especially for nesting: $(cmd1 $(cmd2))",
            )

        return ValidationResult(is_valid=True)

    def _check_general_syntax(self, command: str) -> ValidationResult:
        """
        Check for general syntax issues.

        Validates:
        - Variable assignment syntax
        - Command structure
        """
        stripped = command.strip()

        # Check for invalid variable assignment (= at start without var name)
        if re.match(r"^\s*=", stripped):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid variable assignment: missing variable name before '='",
                error_type=ValidationErrorType.INVALID_SYNTAX,
                position=0,
                suggestion="Add a variable name before '=', e.g., 'VAR=value'",
            )

        # Check for spaces around = in what looks like an assignment
        # Pattern: word = value (spaces around =)
        # But be careful: [ "$var" = "value" ] is valid in test expressions
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s+=", stripped) and not stripped.startswith("["):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid variable assignment: no spaces allowed around '=' in assignments",
                error_type=ValidationErrorType.INVALID_SYNTAX,
                suggestion="Remove spaces around '=', e.g., 'VAR=value' not 'VAR = value'",
            )

        return ValidationResult(is_valid=True)

    def _remove_quoted_content(self, command: str) -> str:
        """
        Remove content inside quotes to simplify pattern matching.

        Returns command with quoted strings replaced by placeholders.
        """
        result = []
        state = QuoteState()
        i = 0

        while i < len(command):
            char = command[i]

            if char == "\\" and not state.in_single_quote:
                i += 2
                if not state.in_any_quote:
                    result.append("__")  # Placeholder for escaped chars
                continue

            if char == "'" and not state.in_double_quote and not state.in_backtick:
                state.in_single_quote = not state.in_single_quote
                if not state.in_single_quote:
                    result.append("__QUOTED__")  # Placeholder
            elif char == '"' and not state.in_single_quote and not state.in_backtick:
                state.in_double_quote = not state.in_double_quote
                if not state.in_double_quote:
                    result.append("__QUOTED__")
            elif char == "`" and not state.in_single_quote:
                state.in_backtick = not state.in_backtick
                if not state.in_backtick:
                    result.append("__SUBST__")
            elif not state.in_any_quote:
                result.append(char)

            i += 1

        return "".join(result)

    def _get_context_around(self, command: str, position: int, context_size: int = 20) -> str:
        """Get a snippet of the command around the given position for error messages."""
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

    This function performs comprehensive validation including:
    - Quote balancing (single, double, backticks)
    - Delimiter balancing (parentheses, braces, brackets)
    - Pipe and operator validation
    - Redirection syntax checking
    - Control structure validation (if/fi, for/done, etc.)
    - Command substitution validation

    Args:
        command: The shell command string to validate.

    Returns:
        ValidationResult with:
        - is_valid: Whether the command is syntactically valid
        - error_message: Detailed description of the error
        - error_type: Category of the error
        - position: Character position where error was detected
        - suggestion: Actionable suggestion to fix the error
    """
    return _validator.validate(command)
