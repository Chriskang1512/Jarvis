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
    settle_seconds: float = 0.22


class ClapDetector:
    """Detect two short high-crest impulses without invoking STT."""

    def __init__(self, settings=None):
        self.settings = settings or ClapDetectorSettings()
        self.last_impulse_at = None
        self.first_clap_at = None
        self.second_clap_at = None

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
                self.reset_pattern()
                return True
            if self.first_clap_at is not None and now - self.first_clap_at > self.settings.max_gap_seconds:
                self.first_clap_at = None
            return False
        if (
            self.last_impulse_at is not None
            and now - self.last_impulse_at < self.settings.refractory_seconds
        ):
            return False
        self.last_impulse_at = now
        if self.second_clap_at is not None:
            self.reset_pattern()
            return False
        if self.first_clap_at is None or now - self.first_clap_at > self.settings.max_gap_seconds:
            self.first_clap_at = now
            return False
        gap = now - self.first_clap_at
        if gap < self.settings.min_gap_seconds:
            return False
        self.second_clap_at = now
        return False

    def reset_pattern(self):
        self.first_clap_at = None
        self.second_clap_at = None


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
