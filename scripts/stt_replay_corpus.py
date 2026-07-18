"""Replay an STT corpus manifest through multiple providers and summarize results."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config import ConfigurationLoader
from jarvis.voice.stt import get_stt_metrics_snapshot, render_stt_metrics_console, reset_stt_metrics

from scripts.stt_replay import (
    configure_console_encoding,
    parse_providers,
    replay_provider,
    write_replay_json,
)


def main():
    """Replay every recorded corpus sample and write an aggregate report."""
    configure_console_encoding()
    args = parse_args()
    manifest_path = Path(args.manifest)
    manifest = read_manifest(manifest_path)
    providers = parse_providers(args.providers)
    config = ConfigurationLoader().load()
    reset_stt_metrics()

    print("========== STT Corpus Replay ==========")
    print(f"Manifest : {manifest_path}")
    print(f"Samples  : {len(manifest.get('samples', []))}")
    print(f"Providers: {', '.join(providers)}")
    print(f"Repeat   : {args.repeat}")
    print("=======================================")

    results = []

    for iteration in range(1, args.repeat + 1):
        for sample in manifest.get("samples", []):
            result_row = replay_sample(sample, providers, args, config, iteration)
            results.extend(result_row["results"])
            if not args.quiet:
                print_sample_summary(result_row)

    snapshot = get_stt_metrics_snapshot()
    print_provider_summary(summarize_results(results))
    print(render_stt_metrics_console(snapshot))
    output_path = write_corpus_report(manifest_path, providers, args, results, snapshot)
    print(f"Corpus report saved: {output_path}")


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Replay all WAV samples from an STT corpus manifest.")
    parser.add_argument(
        "--manifest",
        default="output/stt/corpus/manifest.json",
        help="Path to corpus manifest.json.",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["openai"],
        help="Providers as comma-separated or space-separated values: openai google hybrid.",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Number of replay passes over the corpus.")
    parser.add_argument("--model", default="", help="Override OpenAI STT model.")
    parser.add_argument("--language", default="", help="Override OpenAI STT language.")
    parser.add_argument("--output-json", default="", help="Path to write aggregate corpus report JSON.")
    parser.add_argument("--per-sample-json", action="store_true", help="Also write one replay JSON per sample.")
    parser.add_argument("--quiet", action="store_true", help="Print only final provider summary.")
    return parser.parse_args()


def read_manifest(path):
    """Read corpus manifest JSON."""
    if not path.exists():
        raise SystemExit(f"Manifest not found: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def replay_sample(sample, providers, args, config, iteration):
    """Replay one sample through all requested providers."""
    audio_path = Path(sample.get("audio_path", ""))
    expected_text = str(sample.get("expected_text", ""))

    if not audio_path.exists():
        return {
            "index": sample.get("index", 0),
            "expected_text": expected_text,
            "audio_path": str(audio_path),
            "iteration": iteration,
            "results": [
                {
                    "provider": provider,
                    "status": "failed",
                    "raw_transcript": "",
                    "normalized_transcript": "",
                    "exact_match": False,
                    "semantic_match": False,
                    "latency_ms": 0,
                    "fallback_used": False,
                    "correction_applied": False,
                    "error": "audio_not_found",
                }
                for provider in providers
            ],
        }

    audio_data = audio_path.read_bytes()
    provider_results = []
    sample_args = create_sample_args(args, expected_text)

    for provider in providers:
        result = replay_provider(provider, audio_data, audio_path, sample_args, config)
        result["sample_index"] = sample.get("index", 0)
        result["iteration"] = iteration
        provider_results.append(result)

    if args.per_sample_json:
        write_replay_json(audio_path, sample_args, provider_results, get_stt_metrics_snapshot())

    return {
        "index": sample.get("index", 0),
        "expected_text": expected_text,
        "audio_path": str(audio_path),
        "iteration": iteration,
        "results": provider_results,
    }


def create_sample_args(args, expected_text):
    """Create a lightweight object compatible with stt_replay helpers."""
    return argparse.Namespace(
        providers=args.providers,
        model=args.model,
        language=args.language,
        expected_text=expected_text,
        output_json="",
        no_json=False,
    )


def print_sample_summary(row):
    """Print one compact sample summary."""
    print("")
    print(f"[{row['iteration']}] {row['index']}. {row['expected_text']}")
    print("Provider   Status    Exact  Semantic  Latency  Text")

    for result in row["results"]:
        print(
            f"{result.get('provider', '-'):<10} "
            f"{result.get('status', '-'):<9} "
            f"{yes_no(result.get('exact_match')):<6} "
            f"{yes_no(result.get('semantic_match')):<9} "
            f"{result.get('latency_ms', 0):>6}ms  "
            f"{result.get('semantic_transcript') or result.get('normalized_transcript') or result.get('raw_transcript') or '-'}"
        )


def write_corpus_report(manifest_path, providers, args, results, snapshot):
    """Write aggregate corpus replay report JSON."""
    output_path = Path(args.output_json) if args.output_json else create_corpus_report_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "providers": providers,
        "repeat": args.repeat,
        "results": results,
        "summary": summarize_results(results),
        "metrics": {
            "total_requests": snapshot.total_requests,
            "success_count": snapshot.success_count,
            "failure_count": snapshot.failure_count,
            "fallback_count": snapshot.fallback_count,
            "correction_count": snapshot.correction_count,
            "avg_latency_ms": snapshot.avg_latency_ms,
            "provider_requests": snapshot.provider_requests,
            "provider_success": snapshot.provider_success,
            "provider_failure": snapshot.provider_failure,
        },
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def summarize_results(results):
    """Return provider-level match summary."""
    summary = {}

    for result in results:
        provider = result.get("provider", "unknown")
        row = summary.setdefault(
            provider,
            {
                "total": 0,
                "success": 0,
                "exact": 0,
                "semantic": 0,
                "fallback": 0,
                "latency_ms_total": 0,
            },
        )
        row["total"] += 1
        row["success"] += 1 if result.get("status") == "success" else 0
        row["exact"] += 1 if result.get("exact_match") is True else 0
        row["semantic"] += 1 if result.get("semantic_match") is True else 0
        row["fallback"] += 1 if result.get("fallback_used") else 0
        row["latency_ms_total"] += int(result.get("latency_ms") or 0)

    for row in summary.values():
        total = row["total"] or 1
        row["avg_latency_ms"] = int(row["latency_ms_total"] / total)
        row["success_rate"] = round(row["success"] / total * 100, 1)
        row["exact_rate"] = round(row["exact"] / total * 100, 1)
        row["semantic_rate"] = round(row["semantic"] / total * 100, 1)
        row.pop("latency_ms_total", None)

    return summary


def print_provider_summary(summary):
    """Print provider-level aggregate match rates."""
    print("")
    print("========== Provider Summary ==========")
    print("Provider   Total  Success  Exact  Semantic  Fallback  Avg Latency")

    for provider, row in sorted(summary.items()):
        print(
            f"{provider:<10} "
            f"{row['total']:>5}  "
            f"{row['success_rate']:>6.1f}%  "
            f"{row['exact_rate']:>5.1f}%  "
            f"{row['semantic_rate']:>8.1f}%  "
            f"{row['fallback']:>8}  "
            f"{row['avg_latency_ms']:>6}ms"
        )

    print("======================================")


def create_corpus_report_path():
    """Create a project-local report path."""
    output_dir = Path("output") / "stt"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid4().hex[:6]
    return output_dir / f"corpus_replay_{timestamp}_{unique}.json"


def yes_no(value):
    """Format booleans for console tables."""
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return "-"


if __name__ == "__main__":
    main()
