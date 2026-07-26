from jarvis.input.models import (
    ActivationContext,
    ActivationType,
    InputContext,
    InputEnvelope,
    InputMetadata,
    InputModality,
    InputSource,
    InputType,
)


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
        input_type=InputType.COMMAND,
    ):
        normalized_source = source if isinstance(source, InputSource) else InputSource(str(source))
        normalized_modality = (
            modality if isinstance(modality, InputModality) else InputModality(str(modality))
        )
        wake_method_value = getattr(wake_event, "method", "")
        wake_method = str(getattr(wake_method_value, "value", wake_method_value) or "")
        normalized_type = (
            input_type if isinstance(input_type, InputType) else InputType(str(input_type))
        )
        typed_metadata = normalize_metadata(metadata)
        combined = typed_metadata.to_dict()
        if wake_event is not None:
            combined.setdefault("wake_provider", getattr(wake_event, "provider_id", ""))
        activation = activation_context_from_wake_event(wake_event)
        return InputEnvelope(
            source=normalized_source,
            modality=normalized_modality,
            content=content,
            wake_method=wake_method,
            correlation_id=str(correlation_id or ""),
            metadata=combined,
            context=InputContext(
                activation=activation,
                session_id=str(correlation_id or ""),
                turn_type=normalized_type,
            ),
        )

    def ingest(self, provider, correlation_id="", input_type=InputType.COMMAND):
        """Read one Provider input and normalize it through the common gate."""
        provider_input = provider.read()
        if provider_input is None:
            return None
        return self.create(
            provider_input.source,
            provider_input.modality,
            content=provider_input.content,
            wake_event=provider_input.wake_event,
            correlation_id=correlation_id,
            metadata=provider_input.metadata,
            input_type=input_type,
        )


def normalize_metadata(metadata):
    if isinstance(metadata, InputMetadata):
        return metadata
    return InputMetadata(attributes=dict(metadata or {}))


def activation_context_from_wake_event(wake_event):
    if wake_event is None:
        return ActivationContext()
    method_value = getattr(getattr(wake_event, "method", ""), "value", "")
    activation_types = {
        "voice": ActivationType.WAKE_WORD,
        "clap": ActivationType.DOUBLE_CLAP,
        "keyboard": ActivationType.HOTKEY,
    }
    details = dict(getattr(wake_event, "metadata", {}) or {})
    return ActivationContext(
        activation_type=activation_types.get(method_value, ActivationType.EXTERNAL),
        activation_provider=str(getattr(wake_event, "provider_id", "") or ""),
        activation_phrase=details.get("phrase"),
        activated_at=str(getattr(wake_event, "occurred_at", "") or ""),
        confidence=float(getattr(wake_event, "confidence", 0.0) or 0.0),
        activation_id=str(getattr(wake_event, "event_id", "") or ""),
    )
