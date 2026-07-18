"""Inspect Semantic Transcript Layer results without voice input."""

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.voice.semantic import SemanticTranscriptContext, SemanticTranscriptNormalizer
from jarvis.voice.semantic.graph import EDGE_COMPANY, EntityEdge, EntityGraph, EntityNode


def main():
    """Run a semantic probe."""
    configure_stdout()
    args = parse_args()
    configure_trace(args)
    text, context = build_probe(args)
    normalizer = SemanticTranscriptNormalizer()
    runs = []

    for index in range(max(1, args.repeat)):
        if args.bump_version_after and index >= args.bump_version_after:
            context = replace(context, known_entities_version=f"{context.known_entities_version}-v{index + 1}")

        before_metrics = normalizer.entity_cache.metrics()
        result = normalizer.normalize(text, text, context)
        after_metrics = normalizer.entity_cache.metrics()
        runs.append(build_payload(result, before_metrics, after_metrics, index + 1))

    payload = dict(runs[-1])
    payload["runs"] = runs

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print_human(payload, runs)


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Probe Jarvis semantic entity resolution.")
    parser.add_argument("--text", default="", help="Text to resolve.")
    parser.add_argument(
        "--demo",
        choices=["aya_company"],
        default="",
        help="Run a built-in UTF-8-safe demo.",
    )
    parser.add_argument("--output-json", default="", help="Optional JSON output path.")
    parser.add_argument("--trace", action="store_true", help="Show Jarvis trace output while probing.")
    parser.add_argument("--repeat", type=int, default=1, help="Run the same probe multiple times in one process.")
    parser.add_argument(
        "--bump-version-after",
        type=int,
        default=0,
        help="After N runs, change known_entities_version to demonstrate cache invalidation.",
    )
    return parser.parse_args()


def build_payload(result, before_metrics, after_metrics, run_index):
    """Return a serializable payload for one probe run."""
    cache_status = "hit" if after_metrics["cache_hit"] > before_metrics["cache_hit"] else "miss"

    if after_metrics["cache_invalidations"] > before_metrics["cache_invalidations"]:
        cache_status = "invalidated_miss"

    return {
        "run": run_index,
        "semantic_text": result.semantic_text,
        "confidence": result.confidence,
        "requires_clarification": result.requires_clarification,
        "clarification_question": result.clarification_question,
        "entities": result.entity_dicts(),
        "corrections": result.correction_dicts(),
        "resolver_traces": [
            trace.to_dict() for trace in result.resolver_traces if trace.status == "matched"
        ],
        "history": result.history_dicts(),
        "metrics": {
            "cache_status": cache_status,
            **after_metrics,
            "correction_count": len(result.corrections),
            "correction_avg_confidence": correction_average(result.corrections),
        },
    }


def configure_trace(args):
    """Keep semantic probe output compact unless trace is explicitly requested."""
    if args.trace:
        return

    os.environ["JARVIS_DEBUG_TRACE"] = "false"
    os.environ["JARVIS_TRACE_RAW"] = "false"


def build_probe(args):
    """Return probe text and context."""
    if args.demo == "aya_company":
        graph = EntityGraph()
        graph.add_node(
            EntityNode(
                id="person_aya",
                type="person",
                name="아야",
                aliases=("아야", "アヤ"),
                sources=("memory",),
                confidence_by_source={"memory": 0.92},
            )
        )
        graph.add_node(
            EntityNode(
                id="place_hotel",
                type="place",
                name="호텔",
                aliases=("호텔",),
                sources=("memory",),
            )
        )
        graph.add_edge(
            EntityEdge(
                source_id="person_aya",
                type=EDGE_COMPANY,
                target_id="place_hotel",
                source="memory",
                confidence=0.92,
            )
        )
        return "아야 회사", SemanticTranscriptContext(entity_graph=graph)

    return args.text, SemanticTranscriptContext()


def correction_average(corrections):
    """Return average correction confidence or None when no correction exists."""
    if not corrections:
        return None

    return round(sum(correction.confidence for correction in corrections) / len(corrections), 3)


def print_human(payload, runs):
    """Print a compact human-readable result."""
    print("semantic_text:", payload["semantic_text"])
    print("confidence:", payload["confidence"])
    print("clarification:", payload["requires_clarification"], payload["clarification_question"] or "-")
    print("entities:")
    for entity in payload["entities"]:
        print(
            " - "
            f"{entity.get('id')} type={entity.get('type')} value={entity.get('value')} "
            f"source={entity.get('source')} resolver={entity.get('resolver')} "
            f"confidence={entity.get('confidence')}"
        )
    print("matched_resolvers:")
    for trace in payload["resolver_traces"]:
        print(f" - {trace.get('resolver')} status={trace.get('status')} latency={trace.get('latency_ms')}ms")
    print("metrics:")
    for run in runs:
        metrics = run["metrics"]
        print(
            " - "
            f"run={run['run']} cache_status={metrics['cache_status']} "
            f"cache_hit={metrics['cache_hit']} cache_miss={metrics['cache_miss']} "
            f"cache_invalidations={metrics['cache_invalidations']} "
            f"correction_count={metrics['correction_count']} "
            f"correction_avg_confidence={metrics['correction_avg_confidence']}"
        )


def configure_stdout():
    """Prefer UTF-8 stdout where the host console supports it."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        return


if __name__ == "__main__":
    main()
