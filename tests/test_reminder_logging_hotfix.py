import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from jarvis.debug_trace import trace_event


class TestReminderLoggingHotfix(unittest.TestCase):
    """Test Sprint 5.1 reminder console logging policy."""

    def test_scheduler_tick_is_hidden_from_human_debug_console(self):
        """Check scheduler tick does not pollute the wake-word prompt."""
        output = io.StringIO()

        with patch.dict(os.environ, {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": ""}, clear=False):
            with redirect_stdout(output):
                trace_event("reminder.scheduler.tick", now="2026-07-09T21:16:54", due=0)

        self.assertEqual(output.getvalue(), "")

    def test_scheduler_tick_can_still_emit_raw_trace_when_enabled(self):
        """Check tick remains available for raw TRACE diagnostics."""
        output = io.StringIO()

        with patch.dict(os.environ, {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": "true"}, clear=False):
            with redirect_stdout(output):
                trace_event("reminder.scheduler.tick", now="2026-07-09T21:16:54", due=0)

        self.assertIn("TRACE reminder.scheduler.tick", output.getvalue())

    def test_reminder_trigger_still_prints_human_debug_trace(self):
        """Check actual reminder events still show in debug console."""
        output = io.StringIO()

        with patch.dict(os.environ, {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": ""}, clear=False):
            with redirect_stdout(output):
                trace_event("reminder.trigger", id="reminder-1", title="meeting")

        self.assertIn("[Reminder] trigger", output.getvalue())

    def test_reminder_trigger_starts_on_new_line_for_wake_prompt(self):
        """Check reminder events do not append to the wake-word prompt line."""
        output = io.StringIO()

        with patch.dict(os.environ, {"JARVIS_DEBUG_TRACE": "true", "JARVIS_TRACE_RAW": ""}, clear=False):
            with redirect_stdout(output):
                print("Wake word > ", end="")
                trace_event("reminder.trigger", id="reminder-1", title="meeting")

        self.assertIn("Wake word > \n[Reminder] trigger", output.getvalue())


if __name__ == "__main__":
    unittest.main()
