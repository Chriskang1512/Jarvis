import os
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class PlaybackAttempt:
    """One backend attempt during local audio playback."""

    backend: str
    success: bool
    error: str = ""


@dataclass
class PlaybackResult:
    """Result of one local audio playback attempt."""

    success: bool
    backend: str
    path: str
    file_size: int = 0
    error: str = ""
    blocking: bool = True
    attempts: list[PlaybackAttempt] = field(default_factory=list)


class PlaybackBackend(Protocol):
    """Interface for local audio playback backends."""

    name: str

    def play(self, path):
        """Play one audio file and return after playback is complete."""
        ...


class PowerShellPlaybackBackend:
    """Windows SoundPlayer backend using PlaySync for blocking playback."""

    name = "powershell_soundplayer"

    def __init__(self, executable=None, timeout_seconds=60):
        """Create a PowerShell SoundPlayer backend."""
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def play(self, path):
        """Play a WAV file through System.Media.SoundPlayer.PlaySync."""
        path = resolve_audio_path(path)

        if os.name != "nt":
            return playback_failure(self.name, path, "PowerShell playback is only available on Windows.")

        powershell = self.executable or find_executable("powershell")

        if powershell is None:
            return playback_failure(self.name, path, "PowerShell executable was not found.")

        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$player = New-Object System.Media.SoundPlayer "
                f"'{escape_powershell_string(path)}'; "
                "$player.Load(); "
                "$player.PlaySync()"
            ),
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except Exception as error:
            return playback_failure(self.name, path, str(error))

        if completed.returncode == 0:
            return PlaybackResult(True, self.name, path, get_file_size(path), blocking=True)

        return playback_failure(self.name, path, format_subprocess_error(completed))


class WinsoundPlaybackBackend:
    """Windows winsound backend using synchronous SND_FILENAME playback."""

    name = "winsound"

    def play(self, path):
        """Play a WAV file with winsound and wait for completion."""
        path = resolve_audio_path(path)

        try:
            import winsound
        except ImportError:
            return playback_failure(self.name, path, "winsound module is not available.")

        try:
            flags = winsound.SND_FILENAME | getattr(winsound, "SND_NODEFAULT", 0)
            winsound.PlaySound(path, flags)
        except Exception as error:
            return playback_failure(self.name, path, str(error))

        return PlaybackResult(True, self.name, path, get_file_size(path), blocking=True)


class SimpleAudioPlaybackBackend:
    """Optional simpleaudio backend with blocking wait_done playback."""

    name = "simpleaudio"

    def play(self, path):
        """Play a WAV file with simpleaudio and wait for completion."""
        path = resolve_audio_path(path)

        try:
            import simpleaudio
        except ImportError:
            return playback_failure(self.name, path, "simpleaudio package is not installed.")

        try:
            wave_object = simpleaudio.WaveObject.from_wave_file(path)
            play_object = wave_object.play()
            play_object.wait_done()
        except Exception as error:
            return playback_failure(self.name, path, str(error))

        return PlaybackResult(True, self.name, path, get_file_size(path), blocking=True)


class FileOnlyPlaybackBackend:
    """Fallback backend that only reports where the file was written."""

    name = "file_only"

    def play(self, path):
        """Return a clear failure because no audio backend played the file."""
        path = resolve_audio_path(path)
        return playback_failure(self.name, path, f"Audio file generated but not played: {path}")


class CompositePlaybackBackend:
    """Try playback backends in order until one succeeds."""

    def __init__(self, backends):
        """Create a composite backend."""
        self.backends = list(backends)
        self.name = "+".join(backend.name for backend in self.backends)

    def play(self, path):
        """Try each backend and return the first successful result."""
        last_result = None
        attempts = []

        for backend in self.backends:
            result = backend.play(path)
            last_result = result

            attempts.append(PlaybackAttempt(result.backend, result.success, result.error))

            if result.success:
                result.attempts = attempts
                return result

        if last_result is not None:
            last_result.attempts = attempts
            return last_result

        return playback_failure("none", str(path), "No playback backend was configured.")


def create_default_playback_backend():
    """Create the default local playback backend chain."""
    return CompositePlaybackBackend(create_playback_backend_order())


def create_playback_backend_order():
    """Create a playback backend order from debug configuration."""
    preferred_name = read_playback_backend_name()
    default_backends = [
        PowerShellPlaybackBackend(),
        WinsoundPlaybackBackend(),
        SimpleAudioPlaybackBackend(),
    ]

    if preferred_name in ["", "auto", "default"]:
        return default_backends + [FileOnlyPlaybackBackend()]

    preferred_backend = create_named_playback_backend(preferred_name)

    if preferred_backend is None:
        return default_backends + [FileOnlyPlaybackBackend()]

    remaining_backends = [backend for backend in default_backends if backend.name != preferred_backend.name]
    return [preferred_backend] + remaining_backends + [FileOnlyPlaybackBackend()]


def create_named_playback_backend(name):
    """Create one playback backend from a short config name."""
    normalized_name = name.strip().lower()

    if normalized_name in ["powershell", "powershell_soundplayer", "soundplayer"]:
        return PowerShellPlaybackBackend()

    if normalized_name == "winsound":
        return WinsoundPlaybackBackend()

    if normalized_name in ["simpleaudio", "simple"]:
        return SimpleAudioPlaybackBackend()

    if normalized_name in ["file", "file_only"]:
        return FileOnlyPlaybackBackend()

    return None


def play_wav_file(path, backend=None):
    """Compatibility wrapper for playing one WAV file."""
    active_backend = backend or create_default_playback_backend()
    result = active_backend.play(path)

    if not result.success:
        raise RuntimeError(f"Audio playback failed ({result.backend}): {result.error}")

    return result.backend


def playback_failure(backend, path, error):
    """Create a failed playback result."""
    return PlaybackResult(False, backend, str(path), get_file_size(path), str(error), blocking=True)


def inspect_wav_file(path):
    """Return WAV format metadata for debug traces."""
    metadata = {
        "sample_rate": 0,
        "channels": 0,
        "sample_width": 0,
        "frame_count": 0,
        "duration_sec": 0.0,
        "format_error": "",
    }

    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            metadata["sample_rate"] = sample_rate
            metadata["channels"] = wav_file.getnchannels()
            metadata["sample_width"] = wav_file.getsampwidth()
            metadata["frame_count"] = frame_count

            if sample_rate > 0:
                metadata["duration_sec"] = round(frame_count / sample_rate, 3)
    except Exception as error:
        metadata["format_error"] = str(error)

    return metadata


def normalize_wav_for_windows(path):
    """Rewrite streaming WAV placeholders into standard PCM WAV sizes."""
    path = Path(path)

    try:
        content = path.read_bytes()
    except OSError as error:
        return {"normalized": False, "reason": str(error)}

    normalized_content, reason = create_windows_compatible_wav(content)

    if normalized_content is None:
        return {"normalized": False, "reason": reason}

    path.write_bytes(normalized_content)
    return {"normalized": True, "reason": reason}


def create_windows_compatible_wav(content):
    """Return corrected WAV bytes when RIFF/data sizes use stream placeholders."""
    if len(content) < 44:
        return None, "file too small"

    if content[0:4] != b"RIFF" or content[8:12] != b"WAVE":
        return None, "not a RIFF/WAVE file"

    chunks = read_wav_chunks(content)
    fmt_chunk = next((chunk for chunk in chunks if chunk["id"] == b"fmt "), None)
    data_chunk = next((chunk for chunk in chunks if chunk["id"] == b"data"), None)

    if fmt_chunk is None or data_chunk is None:
        return None, "missing fmt or data chunk"

    riff_size = int.from_bytes(content[4:8], "little")
    data_size = data_chunk["declared_size"]
    actual_data_size = len(data_chunk["data"])

    if riff_size != 0xFFFFFFFF and data_size == actual_data_size:
        return None, "already standard wav"

    return build_pcm_wav(fmt_chunk["data"], data_chunk["data"]), "corrected RIFF/data chunk sizes"


def read_wav_chunks(content):
    """Read WAV chunks, allowing stream-size placeholders."""
    chunks = []
    offset = 12

    while offset + 8 <= len(content):
        chunk_id = content[offset : offset + 4]
        declared_size = int.from_bytes(content[offset + 4 : offset + 8], "little")
        data_start = offset + 8

        if declared_size == 0xFFFFFFFF or data_start + declared_size > len(content):
            data_end = len(content)
        else:
            data_end = data_start + declared_size

        chunks.append(
            {
                "id": chunk_id,
                "declared_size": declared_size,
                "data": content[data_start:data_end],
            }
        )

        if declared_size == 0xFFFFFFFF:
            break

        offset = data_end + (declared_size % 2)

    return chunks


def build_pcm_wav(fmt_data, data):
    """Build a minimal RIFF/WAVE file with correct chunk sizes."""
    fmt_chunk = b"fmt " + len(fmt_data).to_bytes(4, "little") + fmt_data
    data_chunk = b"data" + len(data).to_bytes(4, "little") + data
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    return b"RIFF" + riff_size.to_bytes(4, "little") + b"WAVE" + fmt_chunk + data_chunk


def get_file_size(path):
    """Return file size in bytes, or 0 when unavailable."""
    if path is None:
        return 0

    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def find_executable(executable):
    """Resolve an executable path using PATH or a direct file path."""
    if Path(executable).exists():
        return executable

    return shutil.which(executable)


def resolve_audio_path(path):
    """Return an absolute audio path for OS playback APIs."""
    return str(Path(path).resolve())


def escape_powershell_string(value):
    """Escape one string for single-quoted PowerShell usage."""
    return str(value).replace("'", "''")


def format_subprocess_error(completed):
    """Return a compact subprocess failure message."""
    stderr = (completed.stderr or "").strip()
    stdout = (completed.stdout or "").strip()

    if stderr:
        return stderr

    if stdout:
        return stdout

    return f"process exited with code {completed.returncode}"


def read_playback_backend_name():
    """Read JARVIS_PLAYBACK_BACKEND from process env or local .env."""
    value = os.environ.get("JARVIS_PLAYBACK_BACKEND", "")

    if value != "":
        return value

    return read_env_file_value("JARVIS_PLAYBACK_BACKEND")


def read_env_file_value(key):
    """Read one value from a local .env file."""
    env_path = Path(".env")

    if not env_path.exists():
        return ""

    with env_path.open("r", encoding="utf-8") as file:
        for line in file:
            env_key, value = parse_env_line(line)

            if env_key == key:
                return value

    return ""


def parse_env_line(line):
    """Parse a simple KEY=VALUE line."""
    stripped_line = line.strip()

    if stripped_line == "" or stripped_line.startswith("#") or "=" not in stripped_line:
        return "", ""

    key, value = stripped_line.split("=", 1)
    return key.strip(), clean_env_value(value)


def clean_env_value(value):
    """Remove simple wrapping quotes."""
    cleaned = value.strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        if cleaned[0] in ["'", '"']:
            return cleaned[1:-1]

    return cleaned
