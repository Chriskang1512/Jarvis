"""Replay one recorded WAV through STT providers for apples-to-apples testing."""

import argparse
import json
import os
import sys
import wave
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config import ConfigurationLoader
from jarvis.voice.providers import (
    record_microphone_wav_bytes,
    select_stt_fallback_text,
    transcribe_stt_audio,
)
from jarvis.voice.semantic import SemanticTranscriptContext, normalize_semantic_transcript
from jarvis.voice.stt import get_stt_metrics_snapshot, render_stt_metrics_console, reset_stt_metrics
from jarvis.voice.user_vocabulary import format_corrections, normalize_stt_text


def main():
    """Run STT replay for a stored WAV file."""
    configure_console_encoding()
    args = parse_args()
    audio_path = resolve_audio_path(args)

    audio_data = audio_path.read_bytes()
    config = ConfigurationLoader().load()
    providers = parse_providers(args.providers)
    reset_stt_metrics()

    print("========== STT Replay ==========")
    print(f"Audio     : {audio_path}")
    print(f"Duration  : {read_wav_duration_seconds(audio_path):.2f}s")
    print(f"Providers : {', '.join(providers)}")
    if args.expected_text:
        print(f"Expected  : {args.expected_text}")
    print("==============================")

    results = []
    for provider in providers:
        result = replay_provider(provider, audio_data, audio_path, args, config)
        results.append(result)
        print_provider_result(result)

    snapshot = get_stt_metrics_snapshot()
    print(render_stt_metrics_console(snapshot))

    if not args.no_json:
        output_path = write_replay_json(audio_path, args, results, snapshot)
        metrics_path = append_replay_metrics_jsonl(audio_path, args, results)
        print(f"Replay JSON saved: {output_path}")
        print(f"Replay metrics appended: {metrics_path}")


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Replay one WAV through Jarvis STT providers.")
    parser.add_argument("audio", nargs="?", help="Path to a recorded WAV file.")
    parser.add_argument("--record", action="store_true", help="Record one microphone sample before replay.")
    parser.add_argument("--record-output", default="", help="Path to save the recorded WAV.")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["openai"],
        help="Providers as comma-separated or space-separated values: openai google hybrid.",
    )
    parser.add_argument("--model", default="", help="Override OpenAI STT model.")
    parser.add_argument("--language", default="", help="Override OpenAI STT language.")
    parser.add_argument("--expected-text", default="", help="Expected transcript for exact/semantic checks.")
    parser.add_argument("--output-json", default="", help="Path to write replay result JSON.")
    parser.add_argument("--no-json", action="store_true", help="Do not save a replay JSON result.")
    return parser.parse_args()


def configure_console_encoding():
    """Use UTF-8 for replay console IO where supported."""
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


def parse_providers(value):
    """Return normalized provider names."""
    if isinstance(value, (list, tuple)):
        raw_items = []

        for item in value:
            raw_items.extend(str(item or "").split(","))
    else:
        raw_items = str(value or "").split(",")

    providers = [item.strip().lower() for item in raw_items if item.strip()]
    return providers or ["openai"]


def resolve_audio_path(args):
    """Return the WAV path to replay, recording one if requested."""
    if args.record:
        audio_data = record_microphone_wav_bytes()

        if isinstance(audio_data, str):
            raise SystemExit(audio_data)

        output_path = Path(args.record_output) if args.record_output else create_replay_audio_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_data)
        return output_path

    if not args.audio:
        raise SystemExit("Audio file is required unless --record is used.")

    audio_path = Path(args.audio)

    if not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")

    return audio_path


def replay_provider(provider, audio_data, audio_path, args, config):
    """Replay one provider and return a structured result dict."""
    started = perf_counter()

    if provider == "openai":
        raw_text = transcribe_stt_audio(
            audio_data,
            model=args.model or read_stt_model(config),
            language=args.language or read_stt_language(config),
            provider="openai_replay",
            reason="replay",
        )
        return build_replay_result(
            provider=provider,
            raw_text=raw_text,
            latency_ms=elapsed_ms(started),
            expected_text=args.expected_text,
            fallback_used=False,
            status="success" if raw_text else "failed",
        )

    if provider == "google":
        return replay_google(audio_path, args.expected_text, started)

    if provider == "hybrid":
        return replay_hybrid(audio_data, audio_path, args, config, started)

    return build_replay_result(
        provider=provider,
        raw_text="",
        latency_ms=elapsed_ms(started),
        expected_text=args.expected_text,
        status="skipped",
        error="unsupported_provider",
    )


def replay_google(audio_path, expected_text, started=None):
    """Replay one WAV through SpeechRecognition Google STT."""
    started = started or perf_counter()

    try:
        import speech_recognition as sr
    except ImportError as error:
        return build_replay_result(
            provider="google",
            raw_text="",
            latency_ms=elapsed_ms(started),
            expected_text=expected_text,
            status="skipped",
            error=f"speech_recognition_not_available: {error}",
        )

    try:
        recognizer = sr.Recognizer()

        with sr.AudioFile(str(audio_path)) as source:
            audio = recognizer.record(source)

        raw_text = recognizer.recognize_google(audio, language="ko-KR")
        return build_replay_result(
            provider="google",
            raw_text=raw_text,
            latency_ms=elapsed_ms(started),
            expected_text=expected_text,
            fallback_used=False,
            status="success" if raw_text else "failed",
        )
    except Exception as error:
        return build_replay_result(
            provider="google",
            raw_text="",
            latency_ms=elapsed_ms(started),
            expected_text=expected_text,
            status="failed",
            error=str(error),
        )


def replay_hybrid(audio_data, audio_path, args, config, started):
    """Replay a simple Google-primary/OpenAI-fallback STT policy."""
    google_result = replay_google(audio_path, args.expected_text, started=perf_counter())
    google_text = google_result["raw_transcript"] if google_result["status"] == "success" else ""
    fallback_reason = "primary_failed" if google_text == "" else "replay_compare"
    openai_started = perf_counter()
    openai_text = transcribe_stt_audio(
        audio_data,
        model=args.model or read_stt_model(config),
        language=args.language or read_stt_language(config),
        provider="openai_replay_fallback",
        reason=fallback_reason,
    )
    selected = select_stt_fallback_text(
        primary_text=google_text,
        fallback_text=openai_text,
        reason=fallback_reason,
        confirmation_mode=is_confirmation_expected(args.expected_text),
    )
    result = build_replay_result(
        provider="hybrid",
        raw_text=selected,
        latency_ms=elapsed_ms(started),
        expected_text=args.expected_text,
        fallback_used=selected == openai_text and openai_text != google_text,
        status="success" if selected else "failed",
    )
    result["metadata"] = {
        "google": google_result,
        "openai_latency_ms": elapsed_ms(openai_started),
        "openai_text": openai_text,
        "fallback_reason": fallback_reason,
    }
    return result


def build_replay_result(
    provider,
    raw_text,
    latency_ms,
    expected_text="",
    fallback_used=False,
    status="success",
    error="",
):
    """Return one normalized replay result."""
    normalization = normalize_stt_text(raw_text)
    expected_normalization = normalize_stt_text(expected_text)
    normalized = normalization.normalized_text
    expected = expected_normalization.normalized_text
    semantic = normalize_semantic_transcript(raw_text, normalized, default_semantic_context())

    return {
        "provider": provider,
        "status": status,
        "raw_transcript": raw_text,
        "normalized_transcript": normalized,
        "semantic_transcript": semantic.semantic_text,
        "semantic_corrections": semantic.correction_dicts(),
        "resolved_entities": semantic.entity_dicts(),
        "semantic_history": semantic.history_dicts(),
        "resolver_traces": semantic.resolver_trace_dicts(),
        "clarification_required": semantic.requires_clarification,
        "corrections": format_corrections(normalization.corrections),
        "correction_applied": bool(normalization.corrections) or bool(semantic.corrections),
        "latency_ms": latency_ms,
        "fallback_used": fallback_used,
        "expected_text": expected_text,
        "exact_match": exact_match(semantic.semantic_text, expected),
        "semantic_match": semantic_match(semantic.semantic_text, expected),
        "error": error,
    }


def print_provider_result(result):
    """Print a readable replay result line."""
    print(f"[{result['provider']}] status={result['status']} latency={result['latency_ms']}ms")
    print(f"  raw        : {result['raw_transcript'] or '<empty>'}")
    print(f"  normalized : {result['normalized_transcript'] or '<empty>'}")
    print(f"  semantic   : {result.get('semantic_transcript') or '<empty>'}")
    print(f"  fallback   : {'YES' if result['fallback_used'] else 'NO'}")
    print(f"  corrections: {result['corrections'] or []}")
    print(f"  sem corr   : {result.get('semantic_corrections') or []}")

    if result["expected_text"]:
        print(
            "  match      : "
            f"exact={'YES' if result['exact_match'] else 'NO'} "
            f"semantic={'YES' if result['semantic_match'] else 'NO'}"
        )

    if result["error"]:
        print(f"  error      : {result['error']}")


def read_stt_model(config):
    """Return configured STT model."""
    return os.environ.get("JARVIS_STT_OPENAI_MODEL") or getattr(config.stt, "openai_model", "") or "gpt-4o-transcribe"


def read_stt_language(config):
    """Return configured STT language."""
    return os.environ.get("JARVIS_STT_OPENAI_LANGUAGE") or getattr(config.stt, "openai_language", "") or "ko"


def default_semantic_context():
    """Return replay-time semantic context with known local entities."""
    return SemanticTranscriptContext(
        known_people=("아야", "유이", "유리"),
        known_places=("서울역", "롯데월드", "강릉 고용보험공단"),
    )


def exact_match(actual, expected):
    """Return strict normalized text equality."""
    if expected == "":
        return None

    return normalize_for_match(actual) == normalize_for_match(expected)


def semantic_match(actual, expected):
    """Return a lightweight semantic match without invoking an LLM."""
    if expected == "":
        return None

    actual_norm = normalize_for_match(actual)
    expected_norm = normalize_for_match(expected)

    if actual_norm == "" or expected_norm == "":
        return False

    if actual_norm == expected_norm:
        return True

    return expected_norm in actual_norm or actual_norm in expected_norm


def normalize_for_match(text):
    """Normalize text for replay matching."""
    normalized = normalize_korean_number_words(str(text or "").lower())
    normalized = "".join(normalized.split())
    for token in punctuation_tokens_for_match():
        normalized = normalized.replace(token, "")
    return normalized

    for token in [".", ",", "?", "!", "，", "。", "？", "！"]:
        normalized = normalized.replace(token, "")

    return normalized


def normalize_korean_number_words(text):
    """Normalize common Korean spoken numbers used in corpus matching."""
    normalized = str(text or "")
    for source, target in korean_number_word_pairs():
        normalized = normalized.replace(source, target)
    return normalized

    for source, target in [
        ("한 시", "1시"),
        ("두 시", "2시"),
        ("세 시", "3시"),
        ("네 시", "4시"),
        ("다섯 시", "5시"),
        ("여섯 시", "6시"),
        ("일곱 시", "7시"),
        ("여덟 시", "8시"),
        ("아홉 시", "9시"),
        ("열 시", "10시"),
        ("열한 시", "11시"),
        ("열두 시", "12시"),
        ("한시", "1시"),
        ("두시", "2시"),
        ("세시", "3시"),
        ("네시", "4시"),
    ]:
        normalized = normalized.replace(source, target)

    return normalized


def is_confirmation_expected(expected_text):
    """Return whether expected text is a short confirmation answer."""
    return normalize_for_match(expected_text) in ["응", "네", "예", "yes", "ㅇ"]


def korean_number_word_pairs():
    """Return Korean spoken clock-number replacements without source encoding risk."""
    si = "\uc2dc"
    return [
        (f"\ud55c {si}", f"1{si}"),
        (f"\ub450 {si}", f"2{si}"),
        (f"\uc138 {si}", f"3{si}"),
        (f"\ub124 {si}", f"4{si}"),
        (f"\ub2e4\uc12f {si}", f"5{si}"),
        (f"\uc5ec\uc12f {si}", f"6{si}"),
        (f"\uc77c\uacf1 {si}", f"7{si}"),
        (f"\uc5ec\ub35f {si}", f"8{si}"),
        (f"\uc544\ud649 {si}", f"9{si}"),
        (f"\uc5f4 {si}", f"10{si}"),
        (f"\uc5f4\ud55c {si}", f"11{si}"),
        (f"\uc5f4\ub450 {si}", f"12{si}"),
        (f"\ud55c{si}", f"1{si}"),
        (f"\ub450{si}", f"2{si}"),
        (f"\uc138{si}", f"3{si}"),
        (f"\ub124{si}", f"4{si}"),
    ]


def punctuation_tokens_for_match():
    """Return punctuation stripped for corpus matching."""
    return [".", ",", "?", "!", "\uff0c", "\u3002", "\uff1f", "\uff01"]


def elapsed_ms(started):
    """Return elapsed milliseconds since started."""
    return int((perf_counter() - started) * 1000)


def read_wav_duration_seconds(audio_path):
    """Return WAV duration in seconds, or 0 when unavailable."""
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate or 1)
    except (OSError, wave.Error):
        return 0.0


def create_replay_audio_path():
    """Create a project-local path for a newly recorded replay sample."""
    output_dir = Path("output") / "stt"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid4().hex[:6]
    return output_dir / f"replay_audio_{timestamp}_{unique_id}.wav"


def create_replay_json_path():
    """Create a project-local replay JSON path."""
    output_dir = Path("output") / "stt"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid4().hex[:6]
    return output_dir / f"replay_{timestamp}_{unique_id}.json"


def write_replay_json(audio_path, args, results, snapshot):
    """Write replay results to JSON and return the path."""
    output_path = Path(args.output_json) if args.output_json else create_replay_json_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "audio_path": str(audio_path),
        "audio_duration_sec": round(read_wav_duration_seconds(audio_path), 3),
        "expected_text": args.expected_text,
        "providers": parse_providers(args.providers),
        "results": results,
        "metrics": asdict(snapshot),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def append_replay_metrics_jsonl(audio_path, args, results):
    """Append replay results to the long-lived STT metrics JSONL file."""
    metrics_path = Path("output") / "stt" / "metrics.jsonl"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().isoformat(timespec="seconds")

    with metrics_path.open("a", encoding="utf-8") as file:
        for result in results:
            payload = {
                "created_at": created_at,
                "kind": "stt_replay",
                "audio_path": str(audio_path),
                "expected_text": args.expected_text,
                "provider": result.get("provider", ""),
                "status": result.get("status", ""),
                "raw_transcript": result.get("raw_transcript", ""),
                "normalized_transcript": result.get("normalized_transcript", ""),
                "semantic_transcript": result.get("semantic_transcript", ""),
                "semantic_corrections": result.get("semantic_corrections", []),
                "resolved_entities": result.get("resolved_entities", []),
                "semantic_history": result.get("semantic_history", []),
                "resolver_traces": result.get("resolver_traces", []),
                "clarification_required": result.get("clarification_required", False),
                "exact_match": result.get("exact_match"),
                "semantic_match": result.get("semantic_match"),
                "latency_ms": result.get("latency_ms", 0),
                "fallback_used": result.get("fallback_used", False),
                "correction_applied": result.get("correction_applied", False),
                "error": result.get("error", ""),
            }
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return metrics_path


if __name__ == "__main__":
    main()
