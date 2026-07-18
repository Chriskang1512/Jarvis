"""Record a small STT regression corpus as reusable WAV assets."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.voice.providers import record_microphone_wav_bytes


DEFAULT_PHRASES = [
    "응",
    "아야랑 유이",
    "서울역으로 바꿔",
    "아니 15일 2시",
    "내일 오후 3시에 아야 만나기 일정 등록해",
]


def main():
    """Record configured phrases and write a manifest."""
    configure_console_encoding()
    args = parse_args()
    phrases = read_phrases(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "count": len(phrases),
        "samples": [],
    }

    print("========== STT Corpus Recorder ==========")
    print(f"Output : {output_dir}")
    print(f"Count  : {len(phrases)}")
    print("Press Enter before each recording. Ctrl+C to stop.")
    print("=========================================")

    for index, phrase in enumerate(phrases, start=1):
        print("")
        print(f"[{index}/{len(phrases)}] Say: {phrase}")
        input("Ready? Press Enter, then speak clearly... ")
        audio_data = record_microphone_wav_bytes()

        if isinstance(audio_data, str):
            print(f"  failed: {audio_data}")
            manifest["samples"].append(
                {
                    "index": index,
                    "expected_text": phrase,
                    "status": "failed",
                    "error": audio_data,
                }
            )
            continue

        wav_path = output_dir / create_sample_filename(index, phrase)
        wav_path.write_bytes(audio_data)
        sample = {
            "index": index,
            "expected_text": phrase,
            "audio_path": str(wav_path),
            "size_bytes": len(audio_data),
            "status": "recorded",
        }
        manifest["samples"].append(sample)
        print(f"  saved: {wav_path} ({len(audio_data)} bytes)")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print(f"Manifest saved: {manifest_path}")


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Record reusable STT regression WAV samples.")
    parser.add_argument(
        "--output-dir",
        default="output/stt/corpus",
        help="Directory where WAV samples and manifest.json will be saved.",
    )
    parser.add_argument(
        "--phrases-file",
        default="",
        help="Optional UTF-8 text file with one phrase per line.",
    )
    parser.add_argument(
        "--phrases",
        default="",
        help="Optional pipe-separated phrase list. Example: \"응|아야랑 유이\"",
    )
    return parser.parse_args()


def configure_console_encoding():
    """Use UTF-8 for corpus recording console IO where supported."""
    import os

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    for stream in [sys.stdin, sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def read_phrases(args):
    """Return phrases from CLI, file, or defaults."""
    if args.phrases:
        phrases = [item.strip() for item in args.phrases.split("|")]
        return [item for item in phrases if item]

    if args.phrases_file:
        phrase_path = Path(args.phrases_file)
        return [
            line.strip()
            for line in phrase_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    return list(DEFAULT_PHRASES)


def create_sample_filename(index, phrase):
    """Create a stable, readable filename for one phrase."""
    slug = slugify_phrase(phrase)
    unique = uuid4().hex[:6]
    return f"{index:02d}_{slug}_{unique}.wav"


def slugify_phrase(phrase):
    """Return a short Korean-safe slug for Windows filenames."""
    allowed = []

    for char in str(phrase or ""):
        if char.isalnum():
            allowed.append(char)
        elif char.isspace():
            allowed.append("_")

    slug = "".join(allowed).strip("_")
    slug = "_".join(part for part in slug.split("_") if part)
    return slug[:40] or "sample"


if __name__ == "__main__":
    main()
