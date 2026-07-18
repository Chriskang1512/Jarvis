from dataclasses import dataclass

from jarvis.voice.stt.models import TranscriptResult


@dataclass(frozen=True)
class TranscriptQualityIssue:
    """One quality issue found in a transcript."""

    code: str
    message: str


class TranscriptQualityGate:
    """Small deterministic quality gate for STT transcripts."""

    def evaluate(self, result, expected_answer_type="", pending_field="", confirmation_decision=""):
        """Return quality issues for a transcript."""
        issues = []
        text = normalized_text(result)

        if not result.success:
            issues.append(TranscriptQualityIssue("stt_failed", result.error_message or "STT failed."))

        if text == "":
            issues.append(TranscriptQualityIssue("empty_transcript", "Transcript is empty."))

        if "speech recognition failed" in text.lower():
            issues.append(TranscriptQualityIssue("recognition_failed_text", "Provider returned failure text."))

        if expected_answer_type == "confirmation" and confirmation_decision in ["", "unknown", None]:
            issues.append(TranscriptQualityIssue("confirmation_unknown", "Confirmation answer was not understood."))

        if pending_field == "time" and text and not has_time_signal(text):
            issues.append(TranscriptQualityIssue("missing_time_signal", "Expected a time expression."))

        if pending_field == "date" and text and not has_date_signal(text):
            issues.append(TranscriptQualityIssue("missing_date_signal", "Expected a date expression."))

        return issues


def normalized_text(result):
    """Return a normalized transcript string."""
    if isinstance(result, TranscriptResult):
        return result.display_text().strip()

    return str(result or "").strip()


def has_time_signal(text):
    """Return whether text appears to include a time expression."""
    compact = str(text or "").replace(" ", "")
    return any(token in compact for token in ["시", "분", "오전", "오후"]) or any(char.isdigit() for char in compact)


def has_date_signal(text):
    """Return whether text appears to include a date expression."""
    compact = str(text or "").replace(" ", "")
    return any(token in compact for token in ["오늘", "내일", "모레", "일", "월"]) or any(char.isdigit() for char in compact)
