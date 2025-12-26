import re
from typing import Optional

import questionary
from rich import print as rprint

from zev.llms.types import Workflow

# Pattern to match {{variable_name}} with optional description {{variable_name:description}}
VARIABLE_PATTERN = re.compile(r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([^}]*))?\}\}')


def extract_variables_from_workflow(workflow: Workflow) -> dict[str, Optional[str]]:
    """
    Extract all unique variables from workflow steps.
    Returns a dict mapping variable names to their descriptions (if provided).
    """
    variables: dict[str, Optional[str]] = {}

    for step in workflow.steps:
        matches = VARIABLE_PATTERN.findall(step.command)
        for var_name, description in matches:
            # Keep the first description we find for each variable
            if var_name not in variables:
                variables[var_name] = description if description else None

    return variables


def substitute_variables(command: str, variables: dict[str, str]) -> str:
    """
    Replace all {{variable_name}} or {{variable_name:description}} patterns
    with their values from the variables dict.
    """
    def replace_var(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))

    return VARIABLE_PATTERN.sub(replace_var, command)


def prompt_for_variables(
    variables: dict[str, Optional[str]],
    existing_values: dict[str, str] = None
) -> Optional[dict[str, str]]:
    """
    Prompt the user to enter values for workflow variables.
    Returns a dict of variable names to values, or None if cancelled.

    Args:
        variables: Dict mapping variable names to their descriptions
        existing_values: Previously entered values (for resuming workflows)
    """
    existing_values = existing_values or {}
    result: dict[str, str] = {}

    if not variables:
        return result

    rprint("\n[bold cyan]This workflow requires the following variables:[/bold cyan]\n")

    style = questionary.Style(
        [
            ("qmark", "#98c379"),
            ("question", "#98c379"),
            ("instruction", "italic #646464"),
        ]
    )

    for var_name, description in variables.items():
        # Use existing value as default if available
        default_value = existing_values.get(var_name, "")

        # Build the prompt
        if description:
            prompt_text = f"{var_name} ({description})"
        else:
            # Generate a human-readable prompt from variable name
            readable_name = var_name.replace('_', ' ').title()
            prompt_text = readable_name

        value = questionary.text(
            message=prompt_text,
            default=default_value,
            style=style,
        ).ask()

        if value is None:  # User pressed Ctrl-C
            return None

        result[var_name] = value

    return result


def has_variables(workflow: Workflow) -> bool:
    """Check if a workflow contains any variables."""
    for step in workflow.steps:
        if VARIABLE_PATTERN.search(step.command):
            return True
    return False


def display_variables_summary(variables: dict[str, str]) -> None:
    """Display a summary of variable values."""
    if not variables:
        return

    rprint("\n[dim]Variables:[/dim]")
    for name, value in variables.items():
        # Truncate long values for display
        display_value = value if len(value) <= 50 else value[:47] + "..."
        rprint(f"[dim]  {name} = {display_value}[/dim]")
