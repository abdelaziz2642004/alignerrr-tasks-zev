"""Command validation module for checking shell command syntax and safety."""

import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Optional


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


class CommandValidator:
    """Validates shell commands for syntax errors and malformed constructs."""

    # Shell control flow keywords that must be balanced
    CONTROL_KEYWORDS = {
        "if": "fi",
        "then": None,  # Part of if block
        "elif": None,  # Part of if block
        "else": None,  # Part of if block
        "fi": "if",
        "for": "done",
        "while": "done",
        "until": "done",
        "do": None,  # Part of loop
        "done": ("for", "while", "until"),
        "case": "esac",
        "esac": "case",
        "select": "done",
    }

    def validate(self, command: str) -> ValidationResult:
        """
        Validate a shell command for syntax errors and malformed constructs.

        Performs comprehensive validation including:
        - Empty/whitespace command detection
        - Quote balancing (single, double, backticks)
        - Operator placement (pipes, redirects, logical operators)
        - Delimiter balancing (parentheses, braces, brackets)
        - Pipe chain integrity
        - Redirection target validation
        - Shell control flow keyword balancing

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

        # Check for empty command
        if not command or command.isspace():
            return ValidationResult(
                is_valid=False,
                error_message="Command is empty or contains only whitespace",
                error_code=ValidationErrorCode.EMPTY_COMMAND,
                suggestion="Provide a non-empty shell command",
            )

        # Check for quote balancing with detailed position info
        quote_result = self._check_quotes_detailed(command)
        if not quote_result.is_valid:
            return quote_result

        # Check for trailing operators
        trailing_result = self._check_trailing_operators(command)
        if not trailing_result.is_valid:
            return trailing_result

        # Check for leading operators
        leading_result = self._check_leading_operators(command)
        if not leading_result.is_valid:
            return leading_result

        # Check for balanced delimiters with position tracking
        delimiter_result = self._check_balanced_delimiters_detailed(command)
        if not delimiter_result.is_valid:
            return delimiter_result

        # Check pipe chain integrity
        pipe_result = self._check_pipe_chain_integrity(command)
        if not pipe_result.is_valid:
            return pipe_result

        # Check logical operator chains
        logical_result = self._check_logical_operator_chains(command)
        if not logical_result.is_valid:
            return logical_result

        # Check for malformed redirections
        redirect_result = self._check_redirections_detailed(command)
        if not redirect_result.is_valid:
            return redirect_result

        # Check command structure
        structure_result = self._check_command_structure_detailed(command)
        if not structure_result.is_valid:
            return structure_result

        # Check shell control flow keywords
        control_result = self._check_control_flow_keywords(command)
        if not control_result.is_valid:
            return control_result

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
                # Backslash only escapes in double quotes or outside quotes
                if double_quote_start is not None or (
                    single_quote_start is None and backtick_start is None
                ):
                    escaped = True
                continue

            # Single quotes - no escaping inside
            if char == "'" and double_quote_start is None and backtick_start is None:
                if single_quote_start is None:
                    single_quote_start = i
                else:
                    single_quote_start = None
                continue

            # Double quotes - can be escaped
            if char == '"' and single_quote_start is None and backtick_start is None:
                if double_quote_start is None:
                    double_quote_start = i
                else:
                    double_quote_start = None
                continue

            # Backticks - legacy command substitution
            if char == "`" and single_quote_start is None:
                if backtick_start is None:
                    backtick_start = i
                else:
                    backtick_start = None
                continue

        # Check for unclosed quotes
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

        # Also verify with shlex for edge cases
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

        # Check specific trailing operators with detailed messages
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
            # Single & for background is valid, but &> is redirect
            # Check if it's a redirect pattern
            if len(stripped) >= 2 and stripped[-2] in "<>":
                return ValidationResult(
                    is_valid=False,
                    error_message="Redirection operator missing target file",
                    error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                    error_position=len(stripped) - 1,
                    suggestion="Specify a file after the redirection, e.g., 'cmd &> file'",
                )
            # Background & is valid
            pass

        # Check for trailing redirects without targets
        redirect_match = re.search(r"[<>]+\s*$", stripped)
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
            # Trailing semicolon is technically valid but often indicates incomplete input
            # Be lenient here - only flag if it's just a semicolon
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
        # Track opening positions for better error messages
        paren_stack: list[int] = []
        brace_stack: list[int] = []
        bracket_stack: list[int] = []
        subshell_stack: list[int] = []  # $( positions

        in_single_quote = False
        in_double_quote = False
        in_case_pattern = False  # Track if we're in a case pattern (between 'in' and ')')
        escaped = False
        i = 0

        # Pre-scan for case statements to handle their special syntax
        # Case patterns use ) without matching ( which is valid: case $x in pattern) cmd;;
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

            # Check for $( command substitution
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
                    # In case statements, ) is used for pattern matching without opening (
                    # This is valid syntax: case $x in pattern) commands;;
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

        # Check for unclosed delimiters
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
        # Split command into segments, respecting quotes and subshells
        segments = self._split_by_operator(command, "|", exclude_double=True)

        for i, segment in enumerate(segments):
            stripped = segment.strip()
            if not stripped:
                if i == 0:
                    # Already handled by leading operator check
                    continue
                if i == len(segments) - 1:
                    # Already handled by trailing operator check
                    continue
                # Empty segment in the middle
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Empty command in pipe chain at segment {i + 1}",
                    error_code=ValidationErrorCode.EMPTY_PIPE_SEGMENT,
                    suggestion="Each segment in a pipe chain must contain a command, e.g., 'cmd1 | cmd2 | cmd3'",
                )

        return ValidationResult(is_valid=True)

    def _check_logical_operator_chains(self, command: str) -> ValidationResult:
        """Check for valid logical operator (&&, ||) chain structure."""
        # Check for empty segments between && operators
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

        # Check for empty segments between || operators
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
        # Pattern to find redirections: look for > >> < << with optional fd number
        # This is a simplified check; full parsing would require more complex state machine

        # Check for "< <" which is invalid (not here-string <<<)
        if re.search(r"<\s+<(?!<)", command):
            match = re.search(r"<\s+<(?!<)", command)
            return ValidationResult(
                is_valid=False,
                error_message="Invalid redirection '< <' - did you mean '<<' (here-doc) or '<<<' (here-string)?",
                error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                error_position=match.start() if match else None,
                suggestion="Use '<<' for here-documents or '<<<' for here-strings",
            )

        # Check for "> >" which should be ">>"
        if re.search(r">\s+>(?!>)", command):
            match = re.search(r">\s+>(?!>)", command)
            return ValidationResult(
                is_valid=False,
                error_message="Invalid redirection '> >' - did you mean '>>' (append)?",
                error_code=ValidationErrorCode.REDIRECT_WITHOUT_TARGET,
                error_position=match.start() if match else None,
                suggestion="Use '>>' without space for append redirection",
            )

        return ValidationResult(is_valid=True)

    def _check_command_structure_detailed(self, command: str) -> ValidationResult:
        """Check for malformed command structures."""
        # Check for multiple consecutive semicolons, but allow ;; in case statements
        # In case statements, ;; is valid syntax to end a pattern block
        words = self._extract_unquoted_words(command)
        has_case = "case" in words

        if not has_case:
            # Only check for ;; outside of case statements
            match = re.search(r";\s*;", command)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Multiple consecutive semicolons at position {match.start()}",
                    error_code=ValidationErrorCode.CONSECUTIVE_SEMICOLONS,
                    error_position=match.start(),
                    suggestion="Remove extra semicolons; use single ';' to separate commands",
                )
        else:
            # In case statements, check for more than 2 consecutive semicolons (;;; is invalid)
            match = re.search(r";;;+", command)
            if match:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Too many consecutive semicolons at position {match.start()}",
                    error_code=ValidationErrorCode.CONSECUTIVE_SEMICOLONS,
                    error_position=match.start(),
                    suggestion="Use ';;' to end case patterns, not more semicolons",
                )

        # Check for invalid variable assignment
        if re.match(r"^\s*=", command):
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
        # Extract words outside quotes
        words = self._extract_unquoted_words(command)

        # Track control flow structures
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
                # done closes for, while, until, or select
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

        # Check for unclosed structures
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
        current = []
        in_single_quote = False
        in_double_quote = False
        paren_depth = 0
        escaped = False
        i = 0

        while i < len(command):
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

                # Check for operator
                if paren_depth == 0 and command[i:].startswith(operator):
                    # For single char operators like |, exclude || if requested
                    if exclude_double and len(operator) == 1:
                        if i + 1 < len(command) and command[i + 1] == operator:
                            current.append(char)
                            i += 1
                            continue

                    segments.append("".join(current))
                    current = []
                    i += len(operator)
                    continue

            current.append(char)
            i += 1

        segments.append("".join(current))
        return segments

    def _extract_unquoted_words(self, command: str) -> list[str]:
        """Extract words from command that are not inside quotes."""
        words = []
        current_word = []
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

    Performs comprehensive validation including:
    - Empty/whitespace command detection
    - Quote balancing (single, double, backticks)
    - Operator placement (pipes, redirects, logical operators)
    - Delimiter balancing (parentheses, braces, brackets)
    - Pipe chain integrity
    - Redirection target validation
    - Shell control flow keyword balancing

    Args:
        command: The shell command string to validate.

    Returns:
        ValidationResult with detailed error information if invalid.
        The result includes:
        - is_valid: bool indicating if the command is syntactically valid
        - error_message: Human-readable description of the error
        - error_code: Categorized error code for programmatic handling
        - error_position: Character position where the error was detected
        - suggestion: Actionable advice on how to fix the error
    """
    return _validator.validate(command)
