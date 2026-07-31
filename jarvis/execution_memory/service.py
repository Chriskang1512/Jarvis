"""Map immutable execution summaries into searchable experience records."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .models import (
    CURRENT_EXECUTION_MEMORY_SCHEMA_VERSION,
    CURRENT_EXECUTION_SUMMARY_VERSION,
    ExecutionMemoryRecord,
    HistoryEntry,
    HistoryType,
    MemoryConfidence,
    MemoryFactType,
    MemoryProvenance,
    RetentionClass,
    SessionReplayReference,
    utc_now,
)
from .redaction import MemoryRedactor
from .search import MemoryIndexer, MemorySearch


class ExecutionMemoryService:
    def __init__(self, repository, *, redactor=None, semantic_provider=None):
        self.repository = repository
        self.redactor = redactor or MemoryRedactor()
        self.indexer = MemoryIndexer(repository)
        self.search = MemorySearch(repository, semantic_provider)

    def remember(self, summary, *, graph, session, goal=None):
        record = self.to_record(
            summary, graph=graph, session=session, goal=goal
        )
        return self.indexer.index(record)

    def to_record(self, summary, *, graph, session, goal=None):
        execution_id = session.session_id
        summary_version = CURRENT_EXECUTION_SUMMARY_VERSION
        record_id = str(
            uuid5(
                NAMESPACE_URL,
                f"jarvis:execution-memory:{execution_id}:{summary_version}",
            )
        )
        capability_by_node = {
            node.node_id: node.capability_id for node in graph.nodes
        }
        histories = [
            HistoryEntry(
                HistoryType.GOAL,
                "Completed",
                metadata={"goalId": graph.goal_id},
            ),
            HistoryEntry(
                HistoryType.EXECUTION,
                summary.outcome.value,
                metadata={
                    "durationSeconds": summary.duration_seconds,
                    "providerCalls": summary.provider_calls,
                },
            ),
        ]
        for node_id, record in session.node_records.items():
            capability = capability_by_node.get(node_id, "")
            verification = record.verification_result
            if verification is not None:
                histories.append(
                    HistoryEntry(
                        HistoryType.VERIFICATION,
                        verification.status.value,
                        node_id,
                        capability,
                        metadata={
                            "verificationLevel": (
                                verification.verification_level.value
                            )
                        },
                    )
                )
            for attempt in record.attempt_history:
                if attempt.attempt_number > 1:
                    histories.append(
                        HistoryEntry(
                            HistoryType.RETRY,
                            attempt.execution_status,
                            node_id,
                            capability,
                            metadata={
                                "attemptNumber": attempt.attempt_number,
                                "errorCategory": attempt.error_category.value,
                            },
                        )
                    )
            if record.error:
                histories.append(
                    HistoryEntry(
                        HistoryType.FAILURE,
                        record.error,
                        node_id,
                        capability,
                    )
                )
        permission_status = {
            "permission_required": "requested",
            "permission_granted": "approved",
            "permission_denied": "denied",
        }
        histories.extend(
            HistoryEntry(
                HistoryType.PERMISSION,
                permission_status[item.event_type],
                item.node_id,
                capability_by_node.get(item.node_id, ""),
                occurred_at=item.occurred_at,
                metadata={
                    "scope": capability_by_node.get(item.node_id, ""),
                    "reason": str(
                        item.details.get(
                            "reason",
                            "capability_permission_requirement",
                        )
                    ),
                },
            )
            for item in session.timeline
            if item.event_type in permission_status
        )
        if summary.replan_count:
            histories.append(
                HistoryEntry(
                    HistoryType.REPLAN,
                    "Completed",
                    metadata={"count": summary.replan_count},
                )
            )
        verification_status = summary.goal_verification_status.value
        node_verifications = tuple(
            record.verification_result
            for record in session.node_records.values()
            if record.verification_result is not None
        )
        if (
            verification_status == "Skipped"
            and node_verifications
            and all(
                item.status.value in {"Passed", "Skipped"}
                for item in node_verifications
            )
        ):
            verification_status = "Passed"
        factual_confidence = (
            1.0 if verification_status == "Passed" else 0.5
        )
        capabilities = tuple(
            item for item in capability_by_node.values() if item
        )
        signature = " ".join(
            (
                str(getattr(goal, "context", None).domain)
                if getattr(goal, "context", None)
                else "",
                *capabilities,
            )
        ).strip()
        safe_metadata = self.redactor.redact_allowlisted(
            {
                "executionOutcome": summary.outcome.value,
                "durationSeconds": summary.duration_seconds,
                "providerCalls": summary.provider_calls,
                "retryCount": summary.retry_count,
                "replanCount": summary.replan_count,
                "verificationFailures": summary.verification_failures,
                "goalVerificationStatus": verification_status,
                "capabilityIds": capabilities,
                "successCriteriaCount": len(
                    getattr(goal, "success_criteria", ()) or ()
                ),
            },
            {
                "executionOutcome",
                "durationSeconds",
                "providerCalls",
                "retryCount",
                "replanCount",
                "verificationFailures",
                "goalVerificationStatus",
                "capabilityIds",
                "successCriteriaCount",
            },
        )
        return ExecutionMemoryRecord(
            CURRENT_EXECUTION_MEMORY_SCHEMA_VERSION,
            summary_version,
            record_id,
            execution_id,
            graph.goal_id,
            session.session_id,
            session.snapshot_id,
            summary.final_graph_id or graph.graph_id,
            signature,
            summary.outcome.value,
            summary.result_hash,
            tuple(histories),
            SessionReplayReference(
                session.session_id,
                (0, max(0, len(session.timeline) - 1)),
                f"checkpoint://{session.session_id}",
                True,
                RetentionClass.STANDARD,
            ),
            MemoryProvenance(
                MemoryFactType.SYSTEM_OBSERVED,
                execution_id,
                generated_at=utc_now(),
                derived_from=(summary.result_hash,),
            ),
            MemoryConfidence(
                factual_confidence,
                0.0,
                verification_status,
            ),
            tags=tuple(
                sorted(
                    {
                        summary.outcome.value,
                        *(item.split(".", 1)[0] for item in capabilities),
                    }
                )
            ),
            redacted_metadata=safe_metadata,
        )

    def history(self, history_type, *, limit=100):
        return self.repository.search_metadata(
            history_types=(history_type,), limit=limit
        )
