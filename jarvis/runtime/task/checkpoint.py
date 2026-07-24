import hashlib
import hmac
import json
from dataclasses import dataclass

from jarvis.runtime.planner.cost import ResumeMode, ResumeValidation


CHECKPOINT_FINGERPRINT_FIELDS = (
    "task_id",
    "plan_version",
    "current_step_id",
    "completed_step_ids",
    "pending_step_ids",
    "step_input_fingerprint",
    "external_operation_id",
    "confirmation_state",
    "draft_version",
    "permission_snapshot",
    "schema_versions",
    "artifact_refs",
    "resume_policy",
)


@dataclass(frozen=True)
class CheckpointResumeValidationResult:
    valid: bool
    code: str
    expected_fingerprint: str
    actual_fingerprint: str
    requested_resume_mode: ResumeMode
    effective_resume_mode: ResumeMode

    @property
    def escalated(self):
        return self.effective_resume_mode != self.requested_resume_mode


def create_checkpoint_fingerprint(checkpoint):
    """Hash only normalized checkpoint identity and safety fields."""
    source = checkpoint if isinstance(checkpoint, dict) else checkpoint_to_dict(checkpoint)
    payload = {
        field: normalize_fingerprint_value(source.get(field))
        for field in CHECKPOINT_FINGERPRINT_FIELDS
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_checkpoint_resume(decision, checkpoint):
    """Compare a bound checkpoint and escalate mismatches to full restart."""
    requires_checkpoint = decision.resume_validation in {
        ResumeValidation.CHECKPOINT,
        ResumeValidation.FULL,
    }
    if not requires_checkpoint:
        return CheckpointResumeValidationResult(
            valid=True,
            code="CHECKPOINT_VALIDATION_NOT_REQUIRED",
            expected_fingerprint=decision.checkpoint_fingerprint,
            actual_fingerprint="",
            requested_resume_mode=decision.resume_mode,
            effective_resume_mode=decision.resume_mode,
        )
    actual = create_checkpoint_fingerprint(checkpoint)
    expected = str(decision.checkpoint_fingerprint or "")
    if not expected:
        return invalid_checkpoint_result(
            "CHECKPOINT_FINGERPRINT_REQUIRED",
            decision,
            expected,
            actual,
        )
    if not hmac.compare_digest(expected, actual):
        return invalid_checkpoint_result(
            "CHECKPOINT_FINGERPRINT_MISMATCH",
            decision,
            expected,
            actual,
        )
    return CheckpointResumeValidationResult(
        valid=True,
        code="CHECKPOINT_FINGERPRINT_VALID",
        expected_fingerprint=expected,
        actual_fingerprint=actual,
        requested_resume_mode=decision.resume_mode,
        effective_resume_mode=decision.resume_mode,
    )


def invalid_checkpoint_result(code, decision, expected, actual):
    return CheckpointResumeValidationResult(
        valid=False,
        code=code,
        expected_fingerprint=expected,
        actual_fingerprint=actual,
        requested_resume_mode=decision.resume_mode,
        effective_resume_mode=ResumeMode.FULL_RESTART,
    )


def checkpoint_to_dict(checkpoint):
    return {
        field: getattr(checkpoint, field, None)
        for field in CHECKPOINT_FINGERPRINT_FIELDS
    }


def normalize_fingerprint_value(value):
    if isinstance(value, dict):
        return {
            str(key): normalize_fingerprint_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [normalize_fingerprint_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
