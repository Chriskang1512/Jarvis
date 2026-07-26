from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class ClapDetectorSettings:
    peak_threshold: float = 0.55
    rms_threshold: float = 0.08
    crest_factor_threshold: float = 3.0
    min_gap_seconds: float = 0.12
    max_gap_seconds: float = 0.8
    refractory_seconds: float = 0.08
    settle_seconds: float = 0.5


class ClapDetector:
    """Detect two short high-crest impulses without invoking STT."""

    def __init__(self, settings=None):
        self.settings = settings or ClapDetectorSettings()
        self.last_impulse_at = None
        self.first_clap_at = None
        self.second_clap_at = None
        self.last_decision = ""
        self.last_diagnostic = {}

    def process(self, samples, timestamp):
        values = tuple(float(sample) for sample in samples)
        if not values:
            return False
        peak = max(abs(sample) for sample in values)
        rms = sqrt(sum(sample * sample for sample in values) / len(values))
        crest = peak / max(rms, 1e-9)
        is_impulse = (
            peak >= self.settings.peak_threshold
            and rms >= self.settings.rms_threshold
            and crest >= self.settings.crest_factor_threshold
        )
        now = float(timestamp)
        if not is_impulse:
            if (
                self.second_clap_at is not None
                and now - self.second_clap_at >= self.settings.settle_seconds
            ):
                first_clap_at = self.first_clap_at
                second_clap_at = self.second_clap_at
                self.reset_pattern()
                self.last_decision = "CONFIRMED"
                self.set_diagnostic(
                    "CONFIRMED",
                    first_clap_at=first_clap_at,
                    second_clap_at=second_clap_at,
                    gap_seconds=second_clap_at - first_clap_at,
                )
                return True
            if self.first_clap_at is not None and now - self.first_clap_at > self.settings.max_gap_seconds:
                self.first_clap_at = None
            return False
        if (
            self.last_impulse_at is not None
            and now - self.last_impulse_at < self.settings.refractory_seconds
        ):
            self.set_diagnostic(
                "REJECTED",
                rejection_reason="refractory",
                first_clap_at=self.first_clap_at,
                second_clap_at=self.second_clap_at,
                gap_seconds=now - self.last_impulse_at,
            )
            return False
        self.last_impulse_at = now
        if self.second_clap_at is not None:
            first_clap_at = self.first_clap_at
            second_clap_at = self.second_clap_at
            self.reset_pattern()
            self.last_decision = "TRIPLE_CANCELLED"
            self.set_diagnostic(
                "TRIPLE_CANCELLED",
                rejection_reason="third_clap",
                first_clap_at=first_clap_at,
                second_clap_at=second_clap_at,
                gap_seconds=now - second_clap_at,
            )
            return False
        if self.first_clap_at is None:
            self.first_clap_at = now
            self.last_decision = "FIRST_CLAP"
            self.set_diagnostic("FIRST_CLAP", first_clap_at=now)
            return False
        gap = now - self.first_clap_at
        if gap > self.settings.max_gap_seconds:
            previous_first_clap_at = self.first_clap_at
            self.first_clap_at = now
            self.last_decision = "FIRST_CLAP"
            self.set_diagnostic(
                "FIRST_CLAP",
                rejection_reason="gap_above_max",
                first_clap_at=previous_first_clap_at,
                second_clap_at=now,
                gap_seconds=gap,
            )
            return False
        if gap < self.settings.min_gap_seconds:
            self.set_diagnostic(
                "REJECTED",
                rejection_reason="gap_below_min",
                first_clap_at=self.first_clap_at,
                second_clap_at=now,
                gap_seconds=gap,
            )
            return False
        self.second_clap_at = now
        self.last_decision = "DOUBLE_PENDING"
        self.set_diagnostic(
            "DOUBLE_PENDING",
            first_clap_at=self.first_clap_at,
            second_clap_at=now,
            gap_seconds=gap,
        )
        return False

    def reset_pattern(self):
        self.first_clap_at = None
        self.second_clap_at = None

    def pop_decision(self):
        decision = self.last_decision
        self.last_decision = ""
        return decision

    def set_diagnostic(
        self,
        detector_state,
        *,
        rejection_reason="",
        first_clap_at=None,
        second_clap_at=None,
        gap_seconds=None,
    ):
        self.last_diagnostic = {
            "detector_state": detector_state,
            "rejection_reason": rejection_reason,
            "first_clap_at": first_clap_at,
            "second_clap_at": second_clap_at,
            "gap_seconds": gap_seconds,
        }

    def pop_diagnostic(self):
        diagnostic = dict(self.last_diagnostic)
        self.last_diagnostic = {}
        return diagnostic


class SoundDeviceClapMonitor:
    """Fan out normalized microphone frames to wake detectors before STT starts."""

    def __init__(self, on_audio, sample_rate=16000, block_size=800, device=None):
        self.listeners = [on_audio] if on_audio is not None else []
        self.sample_rate = int(sample_rate)
        self.block_size = int(block_size)
        self.device = device
        self.stream = None
        self.started_at = 0.0

    def add_listener(self, on_audio):
        if on_audio not in self.listeners:
            self.listeners.append(on_audio)

    def start(self):
        if self.stream is not None:
            return True
        try:
            import sounddevice
            from time import monotonic

            self.started_at = monotonic()

            def callback(indata, frames, time_info, status):
                del frames, time_info, status
                samples = tuple(float(item[0]) for item in indata)
                timestamp = monotonic()
                for listener in tuple(self.listeners):
                    listener(samples, timestamp)

            self.stream = sounddevice.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device,
                channels=1,
                dtype="float32",
                callback=callback,
            )
            self.stream.start()
            return True
        except (ImportError, OSError, RuntimeError, ValueError):
            self.stream = None
            return False

    def stop(self):
        stream = self.stream
        self.stream = None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except (OSError, RuntimeError):
            return
