class WakeWordListener:
    """Simple wake word listener for the voice pipeline foundation."""

    def __init__(self, wake_word, aliases=()):
        """Create a wake word listener with one configured phrase."""
        self.wake_word = wake_word.lower()
        self.wake_words = tuple(
            dict.fromkeys(
                " ".join(str(item or "").strip().lower().split())
                for item in (wake_word, *tuple(aliases))
                if str(item or "").strip()
            )
        )

    def wait_for_wake_word(self):
        """Wait until the user enters the configured wake word."""
        while True:
            heard_text = input("Wake word > ").strip().lower()

            if heard_text in self.wake_words:
                return heard_text

            print(f"Waiting for '{self.wake_word}'...")
