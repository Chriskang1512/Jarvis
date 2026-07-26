from jarvis.input.models import InputEnvelope, InputModality, InputSource


class InputManager:
    """Normalize heterogeneous provider input into one immutable envelope."""

    def create(
        self,
        source,
        modality,
        content=None,
        wake_event=None,
        correlation_id="",
        metadata=None,
    ):
        normalized_source = source if isinstance(source, InputSource) else InputSource(str(source))
        normalized_modality = (
            modality if isinstance(modality, InputModality) else InputModality(str(modality))
        )
        wake_method_value = getattr(wake_event, "method", "")
        wake_method = str(getattr(wake_method_value, "value", wake_method_value) or "")
        combined = dict(metadata or {})
        if wake_event is not None:
            combined.setdefault("wake_provider", getattr(wake_event, "provider_id", ""))
        return InputEnvelope(
            source=normalized_source,
            modality=normalized_modality,
            content=content,
            wake_method=wake_method,
            correlation_id=str(correlation_id or ""),
            metadata=combined,
        )
