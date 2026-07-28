from threading import Event, RLock, Thread
from time import monotonic, sleep

from jarvis.wake.models import WakeMethod, WakeSettings


class WakeManager:
    """Select the first enabled Wake Provider event by profile priority."""

    def __init__(self, providers=(), settings=None, legacy_listener=None):
        self.settings = settings or WakeSettings()
        self.providers = {provider.method: provider for provider in providers}
        self.legacy_listener = legacy_listener
        self.last_event = None
        self._legacy_thread = None
        self._legacy_result = []
        self._pause_event = Event()
        self._provider_lock = RLock()
        self._providers_active = False
        self.pause_reason = ""

    def wait(self, timeout=None):
        deadline = None if timeout is None else monotonic() + max(0.0, float(timeout))
        self.wait_until_resumed(deadline)
        self.start_enabled_providers()
        self.start_legacy_listener()
        try:
            while True:
                if self._pause_event.is_set():
                    self.stop_enabled_providers()
                    self.clear_pending_events()
                    self.wait_until_resumed(deadline)
                    self.start_enabled_providers()
                if self._legacy_result:
                    heard = self._legacy_result.pop(0)
                    provider = self.providers.get(WakeMethod.VOICE)
                    if provider is None:
                        return heard
                    provider.feed_text(heard)
                    self._legacy_thread = None
                for method in self.settings.profile.priority:
                    if method not in self.settings.profile.enabled:
                        continue
                    provider = self.providers.get(method)
                    event = provider.poll() if provider is not None else None
                    if event is not None:
                        self.last_event = event
                        self.clear_pending_events()
                        return event
                if deadline is not None and monotonic() >= deadline:
                    return None
                sleep(self.settings.polling_interval_seconds)
        finally:
            self.stop_enabled_providers()

    def wait_for_wake_word(self):
        """Compatibility entry point for the existing VoicePipeline."""
        return self.wait()

    def start_enabled_providers(self):
        with self._provider_lock:
            if self._pause_event.is_set() or self._providers_active:
                return
            for method in self.settings.profile.enabled:
                provider = self.providers.get(method)
                start = getattr(provider, "start", None)
                if callable(start):
                    start()
            self._providers_active = True

    def stop_enabled_providers(self):
        with self._provider_lock:
            if not self._providers_active:
                return
            for method in self.settings.profile.enabled:
                provider = self.providers.get(method)
                stop = getattr(provider, "stop", None)
                if callable(stop):
                    stop()
            self._providers_active = False

    def clear_pending_events(self):
        """Prevent simultaneous providers from waking the next session."""
        for provider in self.providers.values():
            clear_pending = getattr(provider, "clear_pending", None)
            if callable(clear_pending):
                clear_pending()

    def start_legacy_listener(self):
        if self.legacy_listener is None:
            return
        if self._legacy_thread is not None and self._legacy_thread.is_alive():
            return

        def listen():
            self._legacy_result.append(self.legacy_listener.wait_for_wake_word())

        self._legacy_thread = Thread(target=listen, name="jarvis-wake-word", daemon=True)
        self._legacy_thread.start()

    def pause(self, reason="external_interaction"):
        """Stop wake audio and reject pending wake events until resumed."""
        self.pause_reason = str(reason or "external_interaction")
        self._pause_event.set()
        self.stop_enabled_providers()
        self.clear_pending_events()

    def resume(self, reason=""):
        """Allow the waiting wake loop to start providers again."""
        del reason
        self.pause_reason = ""
        self.clear_pending_events()
        self._pause_event.clear()

    def is_paused(self):
        return self._pause_event.is_set()

    def wait_until_resumed(self, deadline=None):
        while self._pause_event.is_set():
            if deadline is not None and monotonic() >= deadline:
                return
            sleep(self.settings.polling_interval_seconds)
