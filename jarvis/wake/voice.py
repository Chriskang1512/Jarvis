from io import BytesIO
from math import sqrt
from queue import Empty, Queue
from struct import pack
from threading import Event, Thread
from wave import open as open_wave


class SpeechSegmenter:
    """Extract short speech candidates from an always-on wake microphone."""

    def __init__(
        self,
        on_segment,
        sample_rate=16000,
        min_seconds=0.25,
        max_seconds=3.0,
        silence_seconds=0.45,
    ):
        self.on_segment = on_segment
        self.sample_rate = int(sample_rate)
        self.min_samples = int(self.sample_rate * float(min_seconds))
        self.max_samples = int(self.sample_rate * float(max_seconds))
        self.silence_seconds = float(silence_seconds)
        self.noise_rms = 0.001
        self.frames = []
        self.speech_started_at = None
        self.last_speech_at = None
        self.speech_blocks = 0
        self.active_run_blocks = 0
        self.max_active_run_blocks = 0

    def process(self, samples, timestamp):
        values = tuple(float(value) for value in samples)
        if not values:
            return
        rms = sqrt(sum(value * value for value in values) / len(values))
        start_threshold = max(0.003, self.noise_rms * 3.5)
        continue_threshold = max(0.002, self.noise_rms * 2.0)

        if self.speech_started_at is None:
            if rms < start_threshold:
                self.noise_rms = (self.noise_rms * 0.96) + (rms * 0.04)
                self.speech_blocks = 0
                return
            self.speech_blocks += 1
            if self.speech_blocks < 2:
                return
            self.speech_started_at = float(timestamp)
            self.last_speech_at = float(timestamp)
            self.frames = [values]
            self.active_run_blocks = self.speech_blocks
            self.max_active_run_blocks = self.speech_blocks
            return

        self.frames.append(values)
        if rms >= continue_threshold:
            self.last_speech_at = float(timestamp)
            self.active_run_blocks += 1
            self.max_active_run_blocks = max(
                self.max_active_run_blocks,
                self.active_run_blocks,
            )
        else:
            self.active_run_blocks = 0
        sample_count = sum(len(frame) for frame in self.frames)
        silent_for = float(timestamp) - float(self.last_speech_at)
        if sample_count >= self.max_samples or silent_for >= self.silence_seconds:
            self.finish()

    def finish(self):
        samples = tuple(value for frame in self.frames for value in frame)
        self.frames = []
        self.speech_started_at = None
        self.last_speech_at = None
        self.speech_blocks = 0
        active_run_blocks = self.max_active_run_blocks
        self.active_run_blocks = 0
        self.max_active_run_blocks = 0
        if len(samples) >= self.min_samples and active_run_blocks >= 4:
            self.on_segment(create_wav_bytes(samples, self.sample_rate))


class WakePhraseTranscriber:
    """Transcribe wake candidates away from the realtime audio callback."""

    def __init__(self, transcribe, on_text):
        self.transcribe = transcribe
        self.on_text = on_text
        self.queue = Queue(maxsize=2)
        self.stop_event = Event()
        self.thread = None

    def submit(self, audio_data):
        if self.queue.full():
            return False
        self.queue.put_nowait(audio_data)
        return True

    def start(self):
        if (
            self.thread is not None
            and self.thread.is_alive()
            and not self.stop_event.is_set()
        ):
            return
        # Give every monitoring generation its own queue and cancellation flag.
        # A slow STT request from a stopped generation can then neither consume
        # new audio nor publish a stale wake phrase after monitoring resumes.
        self.queue = Queue(maxsize=2)
        self.stop_event = Event()
        run_queue = self.queue
        run_stop_event = self.stop_event
        self.thread = Thread(
            target=self.run,
            args=(run_queue, run_stop_event),
            name="jarvis-voice-wake",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        thread = self.thread
        run_queue = self.queue
        self.stop_event.set()
        if thread is not None:
            thread.join(timeout=1.0)
        if self.thread is thread:
            self.thread = None
        while True:
            try:
                run_queue.get_nowait()
            except Empty:
                break

    def run(self, run_queue=None, run_stop_event=None):
        queue = run_queue or self.queue
        stop_event = run_stop_event or self.stop_event
        while not stop_event.is_set():
            try:
                audio_data = queue.get(timeout=0.1)
            except Empty:
                continue
            text = self.transcribe(audio_data)
            if text and not stop_event.is_set():
                self.on_text(text)


def create_wav_bytes(samples, sample_rate):
    output = BytesIO()
    pcm = b"".join(
        pack("<h", max(-32768, min(32767, int(float(sample) * 32767))))
        for sample in samples
    )
    with open_wave(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm)
    return output.getvalue()
