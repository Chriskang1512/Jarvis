from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from uuid import uuid4


class InputSource(str, Enum):
    VOICE = "voice"
    KEYBOARD = "keyboard"
    CLIPBOARD = "clipboard"
    OCR = "ocr"
    IMAGE = "image"
    FILE = "file"
    DRAG_DROP = "drag_drop"
    MOBILE = "mobile"
    API = "api"
    TOUCH_PORTAL = "touch_portal"


class InputModality(str, Enum):
    AUDIO = "audio"
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    TRIGGER = "trigger"


@dataclass(frozen=True)
class InputEnvelope:
    """Provider-neutral input delivered to Planner-facing code."""

    source: InputSource
    modality: InputModality
    content: object = field(default=None, repr=False, compare=False)
    input_id: str = ""
    created_at: str = ""
    wake_method: str = ""
    correlation_id: str = ""
    metadata: dict = field(default_factory=dict)
    content_fingerprint: str = ""

    def __post_init__(self):
        if not self.input_id:
            object.__setattr__(self, "input_id", f"IN-{uuid4().hex[:10].upper()}")
        if not self.created_at:
            object.__setattr__(
                self,
                "created_at",
                datetime.now().isoformat(timespec="milliseconds"),
            )
        object.__setattr__(self, "metadata", dict(self.metadata))
        if not self.content_fingerprint:
            encoded = str(self.content if self.content is not None else "").encode("utf-8")
            object.__setattr__(self, "content_fingerprint", sha256(encoded).hexdigest())

    def to_dict(self, include_content=False):
        data = {
            "input_id": self.input_id,
            "source": self.source.value,
            "modality": self.modality.value,
            "created_at": self.created_at,
            "wake_method": self.wake_method,
            "correlation_id": self.correlation_id,
            "metadata": dict(self.metadata),
            "content_fingerprint": self.content_fingerprint,
        }
        if include_content:
            data["content"] = self.content
        return data
