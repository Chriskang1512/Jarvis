from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from jarvis.input.models import InputModality, InputSource


@dataclass(frozen=True)
class ProviderInput:
    source: InputSource
    modality: InputModality
    content: object = field(default=None, repr=False)
    wake_event: object = field(default=None, repr=False)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "metadata", dict(self.metadata))


class InputProvider(Protocol):
    provider_id: str

    def read(self) -> ProviderInput | None:
        ...


class QueueInputProvider:
    """Base adapter for platform input callbacks and future transports."""

    source = InputSource.API
    modality = InputModality.TEXT

    def __init__(self, provider_id):
        self.provider_id = str(provider_id)
        self._inputs = deque()

    def submit(self, content, wake_event=None, metadata=None):
        self._inputs.append(
            ProviderInput(
                source=self.source,
                modality=self.modality,
                content=content,
                wake_event=wake_event,
                metadata={"input_provider": self.provider_id, **dict(metadata or {})},
            )
        )

    def read(self):
        return self._inputs.popleft() if self._inputs else None


class KeyboardInputProvider(QueueInputProvider):
    source = InputSource.KEYBOARD

    def __init__(self):
        super().__init__("keyboard_text")


class ClipboardInputProvider(QueueInputProvider):
    source = InputSource.CLIPBOARD

    def __init__(self):
        super().__init__("clipboard")


class OcrInputProvider(QueueInputProvider):
    source = InputSource.OCR

    def __init__(self):
        super().__init__("ocr_stub")


class ImageInputProvider(QueueInputProvider):
    source = InputSource.IMAGE
    modality = InputModality.IMAGE

    def __init__(self):
        super().__init__("image_stub")


class FileInputProvider(QueueInputProvider):
    source = InputSource.FILE
    modality = InputModality.FILE

    def __init__(self):
        super().__init__("file_stub")


class MobileInputProvider(QueueInputProvider):
    source = InputSource.MOBILE

    def __init__(self):
        super().__init__("mobile_stub")
