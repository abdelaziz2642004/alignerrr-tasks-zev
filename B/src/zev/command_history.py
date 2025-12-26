from pathlib import Path
from typing import Optional

import questionary
from pydantic import BaseModel, ValidationError

from zev.command_selector import show_options
from zev.command_validator import validate_command
from zev.constants import HISTORY_FILE_NAME
from zev.llms.types import Command, OptionsResponse


class CommandHistoryEntry(BaseModel):
    query: str
    response: OptionsResponse


class CommandHistory:
    def __init__(self) -> None:
        self.path = Path.home() / HISTORY_FILE_NAME
        self.max_entries = 100
        self.path.touch(exist_ok=True)
        self.encoding = "utf-8"

    def _filter_valid_commands(self, options: OptionsResponse) -> OptionsResponse:
        """
        Filter out commands with invalid syntax before saving to history.

        Returns a new OptionsResponse with only valid commands.
        """
        valid_commands = []
        for cmd in options.commands:
            result = validate_command(cmd.command)
            if result.is_valid:
                valid_commands.append(cmd)
            # Invalid commands are silently filtered out

        return OptionsResponse(
            commands=valid_commands,
            is_valid=options.is_valid,
            explanation_if_not_valid=options.explanation_if_not_valid,
        )

    def save_options(self, query: str, options: OptionsResponse) -> None:
        """
        Save command options to history after filtering invalid commands.

        Only commands that pass syntax validation are saved to history.
        """
        if options is None:
            return

        # Filter out commands with invalid syntax
        filtered_options = self._filter_valid_commands(options)

        # Don't save if there are no valid commands and the response was marked as valid
        if not filtered_options.commands and options.is_valid:
            return

        entry = CommandHistoryEntry(query=query, response=filtered_options)
        self._write_to_history_file(entry)

    def get_history(self) -> list[CommandHistoryEntry]:
        with open(self.path, "r", encoding=self.encoding) as f:
            entries = [CommandHistoryEntry.model_validate_json(line) for line in f if line.strip()]

        if not entries:
            return None

        return entries

    def _write_to_history_file(self, new_entry: CommandHistoryEntry) -> None:
        with open(self.path, "a", encoding=self.encoding) as f:
            f.write(new_entry.model_dump_json() + "\n")

        # If we've exceeded max entries, trim the file
        with open(self.path, "r", encoding=self.encoding) as f:
            lines = f.readlines()
            if len(lines) > self.max_entries:
                with open(self.path, "w", encoding=self.encoding) as f:
                    f.writelines(lines[-self.max_entries :])

    def display_history_options(self, reverse_history_entries, show_limit=5) -> Optional[CommandHistoryEntry]:
        if not reverse_history_entries:
            print("No command history found")
            return None

        style = questionary.Style(
            [
                ("answer", "fg:#61afef"),
                ("question", "bold"),
                ("instruction", "fg:#98c379"),
            ]
        )

        query_options = [questionary.Choice(entry.query, value=entry) for entry in reverse_history_entries[:show_limit]]

        if len(reverse_history_entries) > show_limit:
            query_options.append(questionary.Choice("Show more...", value="show_more"))

        query_options.append(questionary.Separator())
        query_options.append(questionary.Choice("Cancel"))

        selected = questionary.select(
            "Select from history:", choices=query_options, use_shortcuts=True, style=style
        ).ask()

        if selected == "show_more":
            all_options = [questionary.Choice(entry.query, value=entry) for entry in reverse_history_entries]
            all_options.append(questionary.Separator())
            all_options.append(questionary.Choice("Cancel"))

            return questionary.select(
                "Select from history (showing all items):", choices=all_options, use_shortcuts=True, style=style
            ).ask()

        return selected

    def show_history(self):
        history_entries = self.get_history()
        if not history_entries:
            print("No command history found")
            return

        selected_entry = self.display_history_options(list(reversed(history_entries)))

        if selected_entry in (None, "Cancel"):
            return

        commands = selected_entry.response.commands

        if not commands:
            print("No commands available")
            return None

        show_options(commands)
