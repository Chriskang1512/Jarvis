from datetime import datetime

from jarvis.result_merge.contracts import UnifiedResult, result_merge_timestamp


SUCCESS_STATUSES = {"success", "completed", "ok"}
WARNING_STATUSES = {"warning", "warn", "completed_with_warning"}
FAILED_STATUSES = {"failed", "failure", "error"}


class DefaultResultMerger:
    """Deterministic result merger for execution graph outputs."""

    def merge(self, results, metadata=None):
        """Merge node outputs into results, warnings, errors, and metadata."""
        run_metadata = dict(metadata or {})
        node_results = list(results)
        merged_results = []
        warnings = []
        errors = []

        for node_result in node_results:
            item = normalize_result_item(node_result)
            status = normalize_status(item.get("status", ""))

            if status in SUCCESS_STATUSES:
                merged_results.append(build_result_entry(item))
                warnings.extend(extract_embedded_warnings(item))
            elif status in WARNING_STATUSES:
                warnings.append(build_issue_entry(item))
                result_value = item.get("result")
                if should_keep_warning_result(result_value):
                    merged_results.append(build_result_entry(item))
            elif status in FAILED_STATUSES:
                errors.append(build_issue_entry(item))
            else:
                warnings.append(
                    {
                        "capability": item.get("capability", ""),
                        "node_id": item.get("node_id", ""),
                        "status": item.get("status", ""),
                        "message": "Unknown result status.",
                        "result": item.get("result"),
                    }
                )

        unified_metadata = build_metadata(run_metadata, node_results, merged_results, warnings, errors)
        summary = build_summary(merged_results, warnings, errors)
        return UnifiedResult(
            summary=summary,
            results=tuple(merged_results),
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata=unified_metadata,
        )


def normalize_result_item(node_result):
    """Return a dictionary from a result item contract or raw dictionary."""
    if hasattr(node_result, "to_dict"):
        return node_result.to_dict()

    return dict(node_result)


def normalize_status(status):
    """Normalize result status for merge rules."""
    return str(status).lower().strip()


def build_result_entry(item):
    """Build one successful merged result entry."""
    return {
        "capability": item.get("capability", ""),
        "node_id": item.get("node_id", ""),
        "status": item.get("status", ""),
        "result": item.get("result"),
        "metadata": build_node_metadata(item),
    }


def build_issue_entry(item):
    """Build one warning or error entry."""
    result = item.get("result")
    message = extract_message(result)
    return {
        "capability": item.get("capability", ""),
        "node_id": item.get("node_id", ""),
        "status": item.get("status", ""),
        "message": message,
        "result": result,
        "metadata": build_node_metadata(item),
    }


def build_node_metadata(item):
    """Preserve timing metadata for one capability result."""
    started_at = item.get("started_at")
    finished_at = item.get("finished_at")
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": calculate_duration_ms(started_at, finished_at),
    }


def extract_message(result):
    """Extract a readable issue message from a result payload."""
    if isinstance(result, dict):
        for key in ["error", "warning", "message"]:
            if key in result:
                return result[key]

    if result in (None, ""):
        return "No result message."

    return str(result)


def extract_embedded_warnings(item):
    """Promote warnings embedded in a successful result payload."""
    result = item.get("result")

    if not isinstance(result, dict):
        return []

    raw_warnings = result.get("warnings", [])

    if isinstance(raw_warnings, str):
        raw_warnings = [raw_warnings]

    return [
        {
            "capability": item.get("capability", ""),
            "node_id": item.get("node_id", ""),
            "status": "warning",
            "message": str(warning),
            "result": warning,
            "metadata": build_node_metadata(item),
        }
        for warning in raw_warnings
    ]


def should_keep_warning_result(result):
    """Return whether a warning item also carries a useful result payload."""
    if isinstance(result, dict):
        return any(key not in {"warning", "warnings", "message"} for key in result)

    return result not in (None, "")


def build_metadata(run_metadata, node_results, results, warnings, errors):
    """Build run-level metadata without calling other layers."""
    nodes = [normalize_result_item(item) for item in node_results]
    completed_nodes = len([item for item in nodes if normalize_status(item.get("status", "")) in SUCCESS_STATUSES])
    warning_nodes = len([item for item in nodes if normalize_status(item.get("status", "")) in WARNING_STATUSES])
    failed_nodes = len([item for item in nodes if normalize_status(item.get("status", "")) in FAILED_STATUSES])

    return {
        "execution_id": run_metadata.get("execution_id", ""),
        "plan_id": run_metadata.get("plan_id", ""),
        "status": run_metadata.get("status", ""),
        "elapsed_ms": run_metadata.get("elapsed_ms", calculate_elapsed_ms(nodes)),
        "node_count": len(nodes),
        "completed_nodes": run_metadata.get("completed_nodes", completed_nodes),
        "warning_nodes": run_metadata.get("warning_nodes", warning_nodes),
        "failed_nodes": run_metadata.get("failed_nodes", failed_nodes),
        "result_count": len(results),
        "warning_count": len(warnings),
        "error_count": len(errors),
        "timestamp": result_merge_timestamp(),
        "nodes": [
            {
                "node_id": item.get("node_id", ""),
                "capability": item.get("capability", ""),
                "status": item.get("status", ""),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "duration_ms": calculate_duration_ms(item.get("started_at"), item.get("finished_at")),
            }
            for item in nodes
        ],
    }


def build_summary(results, warnings, errors):
    """Build a deterministic voice-friendly summary."""
    parts = [f"{len(results)} capabilities completed"]

    if warnings:
        parts.append(f"{len(warnings)} warnings")

    if errors:
        parts.append(f"{len(errors)} errors")

    return ", ".join(parts)


def calculate_duration_ms(started_at, finished_at):
    """Calculate elapsed milliseconds from ISO timestamps when possible."""
    if not started_at or not finished_at:
        return None

    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None

    return int((finished - started).total_seconds() * 1000)


def calculate_elapsed_ms(nodes):
    """Calculate run elapsed milliseconds from first start to last finish."""
    started_values = [item.get("started_at") for item in nodes if item.get("started_at")]
    finished_values = [item.get("finished_at") for item in nodes if item.get("finished_at")]

    if not started_values or not finished_values:
        return None

    return calculate_duration_ms(min(started_values), max(finished_values))
