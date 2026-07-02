from typing import Protocol

from jarvis.events.types import JarvisStatus


class EventAdapter(Protocol):
    """Protocol for adapters that consume Jarvis events."""

    def handle_event(self, event):
        """Handle one event from the EventBus."""
        ...


class ConsoleEventAdapter:
    """Temporary adapter that prints JarvisState to the console."""

    def handle_event(self, event):
        """Print one Jarvis event in a readable console format."""
        state = event.state
        print(f"{state.status.value.title()}: {state.message}")


class RiveVisualAdapter:
    """Stub adapter for a future Rive Runtime visual layer."""

    def __init__(self):
        """Prepare the Jarvis status to Rive state machine mapping."""
        self.status_to_rive_input = create_rive_status_mapping()

    def handle_event(self, event):
        """Return the future Rive state machine input for this event."""
        return self.status_to_rive_input[event.state.status]


class ElectronVisualAdapter:
    """Stub adapter for a future Electron or React desktop UI."""

    def handle_event(self, event):
        """Return JarvisState for a future Electron renderer."""
        return event.state


class UnityVisualAdapter:
    """Stub adapter for a future Unity renderer."""

    def handle_event(self, event):
        """Return JarvisState for a future Unity renderer."""
        return event.state


def create_rive_status_mapping():
    """Map Jarvis statuses to future Rive state machine inputs."""
    return {
        JarvisStatus.IDLE: "idle",
        JarvisStatus.WAKE: "wake",
        JarvisStatus.LISTENING: "listening",
        JarvisStatus.TRANSCRIBING: "transcribing",
        JarvisStatus.THINKING: "thinking",
        JarvisStatus.SPEAKING: "speaking",
        JarvisStatus.WORKING: "working",
        JarvisStatus.SUCCESS: "success",
        JarvisStatus.ERROR: "error",
    }

