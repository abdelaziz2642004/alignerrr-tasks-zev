from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import questionary
from pydantic import BaseModel

from zev.command_selector import show_options
from zev.constants import FEEDBACK_FILE_NAME, HISTORY_FILE_NAME
from zev.llms.types import OptionsResponse


class FeedbackStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class CommandFeedback(BaseModel):
    command: str
    query: str
    feedback: FeedbackStatus
    timestamp: str
    notes: Optional[str] = None


class PendingFeedback(BaseModel):
    command: str
    query: str
    copied_at: str


class CommandHistoryEntry(BaseModel):
    query: str
    response: OptionsResponse


class CommandHistory:
    def __init__(self) -> None:
        self.path = Path.home() / HISTORY_FILE_NAME
        self.feedback_path = Path.home() / FEEDBACK_FILE_NAME
        self.max_entries = 100
        self.path.touch(exist_ok=True)
        self.feedback_path.touch(exist_ok=True)
        self.encoding = "utf-8"

    def save_options(self, query: str, options: OptionsResponse) -> None:
        entry = CommandHistoryEntry(query=query, response=options)
        self._write_to_history_file(entry)

    def save_feedback(self, command: str, query: str, feedback: FeedbackStatus, notes: Optional[str] = None) -> None:
        entry = CommandFeedback(
            command=command,
            query=query,
            feedback=feedback,
            timestamp=datetime.now().isoformat(),
            notes=notes,
        )
        self._write_to_feedback_file(entry)

    def save_pending_feedback(self, command: str, query: str) -> None:
        """Store a pending feedback request for the next zev run."""
        pending_file = Path.home() / ".zev_pending_feedback"
        pending = PendingFeedback(
            command=command,
            query=query,
            copied_at=datetime.now().isoformat(),
        )
        with open(pending_file, "w", encoding=self.encoding) as f:
            f.write(pending.model_dump_json())

    def get_pending_feedback(self) -> Optional[PendingFeedback]:
        """Check if there's pending feedback from a previous command."""
        pending_file = Path.home() / ".zev_pending_feedback"
        if not pending_file.exists():
            return None
        try:
            with open(pending_file, "r", encoding=self.encoding) as f:
                content = f.read().strip()
                if content:
                    return PendingFeedback.model_validate_json(content)
        except Exception:
            pass
        return None

    def clear_pending_feedback(self) -> None:
        """Remove the pending feedback file."""
        pending_file = Path.home() / ".zev_pending_feedback"
        if pending_file.exists():
            pending_file.unlink()

    def _write_to_feedback_file(self, entry: CommandFeedback) -> None:
        with open(self.feedback_path, "a", encoding=self.encoding) as f:
            f.write(entry.model_dump_json() + "\n")

        # Trim feedback file if needed
        with open(self.feedback_path, "r", encoding=self.encoding) as f:
            lines = f.readlines()
            if len(lines) > self.max_entries:
                with open(self.feedback_path, "w", encoding=self.encoding) as f:
                    f.writelines(lines[-self.max_entries:])

    def get_feedback(self) -> list[CommandFeedback]:
        with open(self.feedback_path, "r", encoding=self.encoding) as f:
            entries = [CommandFeedback.model_validate_json(line) for line in f if line.strip()]
        return entries if entries else []

    def get_feedback_stats(self) -> dict:
        feedback_entries = self.get_feedback()
        if not feedback_entries:
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        stats = {
            "total": len(feedback_entries),
            "success": sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SUCCESS),
            "failed": sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.FAILED),
            "skipped": sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SKIPPED),
        }
        return stats

    def get_command_feedback_history(self, command: str) -> list[CommandFeedback]:
        """Get all feedback entries for a specific command."""
        feedback_entries = self.get_feedback()
        return [e for e in feedback_entries if e.command == command]

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

        show_options(commands, query=selected_entry.query, save_pending_callback=self.save_pending_feedback)

    def _feedback_callback(self, command: str, query: str, feedback_status: str, notes: Optional[str] = None) -> None:
        """Callback to save feedback from command_selector."""
        self.save_feedback(command, query, FeedbackStatus(feedback_status), notes)

    def get_aggregated_stats(self) -> dict:
        """Get detailed aggregated statistics about command feedback."""
        feedback_entries = self.get_feedback()
        if not feedback_entries:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "success_rate": 0.0,
                "command_stats": [],
                "recent_failures": [],
            }

        # Basic counts
        total = len(feedback_entries)
        success = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SUCCESS)
        failed = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.FAILED)
        skipped = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SKIPPED)

        # Calculate success rate (excluding skipped)
        rated = success + failed
        success_rate = (success / rated * 100) if rated > 0 else 0.0

        # Aggregate by command
        command_data: dict[str, dict] = {}
        for entry in feedback_entries:
            cmd = entry.command
            if cmd not in command_data:
                command_data[cmd] = {"success": 0, "failed": 0, "total": 0}
            command_data[cmd]["total"] += 1
            if entry.feedback == FeedbackStatus.SUCCESS:
                command_data[cmd]["success"] += 1
            elif entry.feedback == FeedbackStatus.FAILED:
                command_data[cmd]["failed"] += 1

        # Build command stats list with success rates
        command_stats = []
        for cmd, data in command_data.items():
            rated = data["success"] + data["failed"]
            cmd_success_rate = (data["success"] / rated * 100) if rated > 0 else 0.0
            command_stats.append({
                "command": cmd,
                "total": data["total"],
                "success": data["success"],
                "failed": data["failed"],
                "success_rate": cmd_success_rate,
            })

        # Sort by total usage (most used first)
        command_stats.sort(key=lambda x: x["total"], reverse=True)

        # Get recent failures with notes
        recent_failures = [
            {"command": e.command, "notes": e.notes, "timestamp": e.timestamp}
            for e in reversed(feedback_entries)
            if e.feedback == FeedbackStatus.FAILED
        ][:5]

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "success_rate": success_rate,
            "command_stats": command_stats,
            "recent_failures": recent_failures,
        }

    def get_anonymized_stats(self) -> dict:
        """Get anonymized statistics suitable for export (no commands or queries included)."""
        feedback_entries = self.get_feedback()
        if not feedback_entries:
            return {
                "total_feedback_entries": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "success_rate": 0.0,
                "unique_commands_count": 0,
                "feedback_with_notes_count": 0,
                "date_range": None,
            }

        total = len(feedback_entries)
        success = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SUCCESS)
        failed = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.FAILED)
        skipped = sum(1 for e in feedback_entries if e.feedback == FeedbackStatus.SKIPPED)
        rated = success + failed
        success_rate = (success / rated * 100) if rated > 0 else 0.0

        unique_commands = len(set(e.command for e in feedback_entries))
        with_notes = sum(1 for e in feedback_entries if e.notes)

        timestamps = [e.timestamp for e in feedback_entries]
        date_range = {
            "earliest": min(timestamps),
            "latest": max(timestamps),
        } if timestamps else None

        return {
            "total_feedback_entries": total,
            "success_count": success,
            "failed_count": failed,
            "skipped_count": skipped,
            "success_rate": round(success_rate, 1),
            "unique_commands_count": unique_commands,
            "feedback_with_notes_count": with_notes,
            "date_range": date_range,
        }
