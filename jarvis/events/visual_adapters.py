from jarvis.events.types import JarvisStatus


class VisualAdapter:
    """Base interface for renderers that consume JarvisState events."""

    def handle_event(self, event):
        """Handle one event from the EventBus."""
        raise NotImplementedError("VisualAdapter subclasses must handle events.")


class ConsoleVisualAdapter(VisualAdapter):
    """Temporary renderer that prints JarvisState to the console."""

    def handle_event(self, event):
        """Print one Jarvis event in a readable console format."""
        state = event.state
        print(f"[{event.name.value}] {state.status.value}: {state.message}")


class RiveVisualAdapter(VisualAdapter):
    """Stub renderer for a future Rive Runtime visual layer."""

    def __init__(self):
        """Prepare the Jarvis status to Rive state machine mapping."""
        self.status_to_rive_input = create_rive_status_mapping()

    def handle_event(self, event):
        """Return the future Rive state machine input for this event."""
        return self.status_to_rive_input[event.state.status]


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

