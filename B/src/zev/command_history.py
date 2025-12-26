from pathlib import Path
from typing import Optional

import questionary
from pydantic import BaseModel

from zev.command_selector import show_options
from zev.constants import HISTORY_FILE_NAME
from zev.llms.types import Command, CommandFeedback, OptionsResponse


class CommandHistoryEntry(BaseModel):
    query: str
    response: OptionsResponse


class CommandHistory:
    def __init__(self) -> None:
        self.path = Path.home() / HISTORY_FILE_NAME
        self.max_entries = 100
        self.path.touch(exist_ok=True)
        self.encoding = "utf-8"

    def save_options(self, query: str, options: OptionsResponse) -> None:
        entry = CommandHistoryEntry(query=query, response=options)
        self._write_to_history_file(entry)

    def save_feedback(self, command: Command, feedback: CommandFeedback) -> None:
        """Update the feedback for a specific command in history."""
        history = self.get_history()
        if not history:
            return

        # Find and update the command in history (search from most recent)
        updated = False
        for entry in reversed(history):
            for cmd in entry.response.commands:
                if cmd.command == command.command and cmd.feedback is None:
                    cmd.feedback = feedback
                    updated = True
                    break
            if updated:
                break

        if updated:
            self._rewrite_history(history)

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

    def _rewrite_history(self, history: list[CommandHistoryEntry]) -> None:
        """Rewrite the entire history file with updated entries."""
        with open(self.path, "w", encoding=self.encoding) as f:
            for entry in history:
                f.write(entry.model_dump_json() + "\n")

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

        show_options(commands, on_feedback=self.save_feedback)
