from collections import deque
import re

from jarvis.debug_trace import trace_event
from jarvis.wake.clap import ClapDetector, SoundDeviceClapMonitor
from jarvis.wake.models import WakeEvent, WakeMethod, normalize_phrase
from jarvis.wake.voice import SpeechSegmenter, WakePhraseTranscriber


class QueueWakeProvider:
    """Thread-safe integration boundary for externally produced wake events."""

    method = WakeMethod.API

    def __init__(self, provider_id):
        self.provider_id = str(provider_id)
        self._events = deque()

    def trigger(self, metadata=None, confidence=1.0):
        self._events.append(
            WakeEvent(
                self.method,
                self.provider_id,
                confidence=float(confidence),
                metadata=dict(metadata or {}),
            )
        )

    def poll(self):
        return self._events.popleft() if self._events else None

    def clear_pending(self):
        self._events.clear()


class KeyboardWakeProvider(QueueWakeProvider):
    method = WakeMethod.KEYBOARD

    def __init__(self, hotkey="ctrl+space"):
        super().__init__("keyboard")
        self.hotkey = str(hotkey)

    def press(self, hotkey):
        if normalize_phrase(hotkey) == normalize_phrase(self.hotkey):
            self.trigger({"hotkey": self.hotkey})
            return True
        return False


class TouchPortalWakeProvider(QueueWakeProvider):
    method = WakeMethod.TOUCH_PORTAL

    def __init__(self):
        super().__init__("touch_portal")


class MobileWakeProvider(QueueWakeProvider):
    method = WakeMethod.MOBILE

    def __init__(self):
        super().__init__("mobile_stub")


class ApiWakeProvider(QueueWakeProvider):
    method = WakeMethod.API

    def __init__(self):
        super().__init__("api")


class WakeWordProvider(QueueWakeProvider):
    method = WakeMethod.VOICE

    def __init__(self, phrases=("hey jarvis", "헤이 자비스", "자비스")):
        super().__init__("wake_word")
        self.phrases = tuple(normalize_phrase(item) for item in phrases)

    def feed_text(self, text):
        normalized = normalize_phrase(text)
        compact = canonical_wake_phrase(normalized)
        if any(
            compact == canonical_wake_phrase(phrase)
            for phrase in self.phrases
        ):
            self.trigger({"phrase": normalized})
            return True
        return False


def canonical_wake_phrase(value):
    return re.sub(r"[\W_]+", "", normalize_phrase(value), flags=re.UNICODE)


class MicrophoneWakeWordProvider(WakeWordProvider):
    """Recognize configured wake phrases from a shared microphone stream."""

    def __init__(self, phrases, transcribe, monitor, sample_rate=16000, max_segment_seconds=1.5):
        super().__init__(phrases)
        self.provider_id = "microphone_wake_word"
        self.monitor = monitor
        self.transcriber = WakePhraseTranscriber(transcribe, self.feed_text)
        self.segmenter = SpeechSegmenter(
            self.transcriber.submit,
            sample_rate=sample_rate,
            max_seconds=max_segment_seconds,
        )
        self.monitor.add_listener(self.segmenter.process)

    def start(self):
        self.transcriber.start()
        return self.monitor.start()

    def stop(self):
        self.monitor.stop()
        self.transcriber.stop()


class ClapWakeProvider(QueueWakeProvider):
    method = WakeMethod.CLAP

    def __init__(self, detector=None, monitor=None, microphone=False, device=None):
        super().__init__("double_clap")
        self.detector = detector or ClapDetector()
        self.monitor = monitor
        if self.monitor is None and microphone:
            self.monitor = SoundDeviceClapMonitor(self.feed_audio, device=device)

    def feed_audio(self, samples, timestamp):
        detected = self.detector.process(samples, timestamp)
        decision = self.detector.pop_decision()
        diagnostic = self.detector.pop_diagnostic()
        if decision or diagnostic:
            trace_event(
                "voice.wake.clap_state",
                state=decision or diagnostic.get("detector_state"),
                timestamp=round(float(timestamp), 3),
                rejection_reason=diagnostic.get("rejection_reason") or "",
                first_clap_at=diagnostic.get("first_clap_at"),
                second_clap_at=diagnostic.get("second_clap_at"),
                gap_seconds=diagnostic.get("gap_seconds"),
                first_threshold=diagnostic.get("first_threshold"),
                second_threshold=diagnostic.get("second_threshold"),
                refractory_elapsed=diagnostic.get("refractory_elapsed"),
                signal_released=diagnostic.get("signal_released"),
                second_candidate_reason=diagnostic.get("second_candidate_reason"),
                activation_count=diagnostic.get("activation_count"),
            )
        if detected:
            self.trigger({"pattern": "double_clap"})
            return True
        return False

    def start(self):
        return self.monitor.start() if self.monitor is not None else True

    def stop(self):
        if self.monitor is not None:
            self.monitor.stop()
