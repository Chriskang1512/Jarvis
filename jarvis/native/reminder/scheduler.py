import threading
from time import sleep


class ReminderScheduler:
    """Background scheduler loop for reminder checks."""

    def __init__(self, engine, interval_seconds=1.0):
        """Create scheduler."""
        self.engine = engine
        self.interval_seconds = float(interval_seconds)
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Start the scheduler in a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the scheduler."""
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 1.0)

    def run_forever(self):
        """Run ticks until stopped."""
        while not self._stop_event.is_set():
            self.engine.tick()
            sleep(self.interval_seconds)
