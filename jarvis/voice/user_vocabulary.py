import json
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_USER_VOCABULARY = {
    "아야": [
        "아이와",
        "아이아",
        "아야와",
        "아야랑",
        "아예",
        "아연",
        "아연와",
        "아연과",
        "Aja",
        "Aja.",
        "aja",
        "aja.",
    ],
    "유이": ["유이", "유이랑"],
    "만나기": ["마나리", "만나리"],
    "서울역": ["설립"],
    "자비스": ["자비스", "자비스야"],
}

DEFAULT_USER_VOCABULARY_PATH = Path("config") / "user_vocabulary.json"
N8N_STT_ALIASES = ["맨발은", "엔에잇엔", "엔팔엔", "nam", "NAM"]


@dataclass(frozen=True)
class VocabularyCorrection:
    """One STT vocabulary correction."""

    source: str
    target: str
    count: int


@dataclass(frozen=True)
class STTNormalizationResult:
    """Normalized STT text and the corrections applied to it."""

    raw_text: str
    normalized_text: str
    corrections: tuple[VocabularyCorrection, ...]


def normalize_stt_text(text, vocabulary=None):
    """Normalize STT text before intent parsing."""
    raw_text = "" if text is None else str(text)
    normalized_text = normalize_spacing(raw_text)
    corrections = []

    for alias in N8N_STT_ALIASES:
        if alias.lower() == "n8":
            normalized_text, count = re.subn(r"(?<![A-Za-z0-9])n8(?!n)", "n8n", normalized_text, flags=re.IGNORECASE)

            if count > 0:
                corrections.append(VocabularyCorrection(source=alias, target="n8n", count=count))

            continue

        count = normalized_text.count(alias)

        if count <= 0:
            continue

        normalized_text = normalized_text.replace(alias, "n8n")
        corrections.append(VocabularyCorrection(source=alias, target="n8n", count=count))

    for alias in WORKFLOW_STT_ALIASES:
        normalized_text, count = re.subn(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            "workflow",
            normalized_text,
            flags=re.IGNORECASE,
        )

        if count > 0:
            corrections.append(VocabularyCorrection(source=alias, target="workflow", count=count))

    for alias in SYSTEM_ECHO_STT_ALIASES:
        normalized_text, count = re.subn(
            re.escape(alias),
            "system.echo",
            normalized_text,
            flags=re.IGNORECASE,
        )

        if count > 0:
            corrections.append(VocabularyCorrection(source=alias, target="system.echo", count=count))

    for canonical, alias in build_alias_pairs(vocabulary or load_user_vocabulary()):
        count = normalized_text.count(alias)

        if count <= 0:
            continue

        normalized_text = normalized_text.replace(alias, canonical)
        corrections.append(VocabularyCorrection(source=alias, target=canonical, count=count))

    return STTNormalizationResult(
        raw_text=raw_text,
        normalized_text=normalized_text.replace("n8nn", "n8n"),
        corrections=tuple(corrections),
    )


def normalize_spacing(text):
    """Collapse noisy whitespace from STT output."""
    return re.sub(r"\s+", " ", text).strip()


def load_user_vocabulary(path=None):
    """Load user vocabulary aliases from config with built-in fallback."""
    vocabulary_path = Path(path) if path is not None else DEFAULT_USER_VOCABULARY_PATH

    if not vocabulary_path.exists():
        return dict(DEFAULT_USER_VOCABULARY)

    try:
        with vocabulary_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_USER_VOCABULARY)

    if not isinstance(data, dict):
        return dict(DEFAULT_USER_VOCABULARY)

    return normalize_vocabulary(data)


def normalize_vocabulary(data):
    """Return vocabulary data in canonical -> aliases list form."""
    vocabulary = {}

    for canonical, aliases in data.items():
        if not isinstance(canonical, str) or canonical.strip() == "":
            continue

        vocabulary[canonical.strip()] = normalize_aliases(aliases)

    return vocabulary


def normalize_aliases(aliases):
    """Return a clean alias list from a config value."""
    if isinstance(aliases, str):
        aliases = [aliases]

    if not isinstance(aliases, list):
        return []

    clean_aliases = []

    for alias in aliases:
        if not isinstance(alias, str):
            continue

        clean_alias = alias.strip()

        if clean_alias == "":
            continue

        clean_aliases.append(clean_alias)

    return clean_aliases


def build_alias_pairs(vocabulary):
    """Return alias pairs sorted so longer aliases are replaced first."""
    pairs = []

    for canonical, aliases in vocabulary.items():
        if not isinstance(canonical, str):
            continue

        canonical = canonical.strip()

        if canonical == "":
            continue

        for alias in aliases:
            if alias == canonical:
                continue

            pairs.append((canonical, alias))

    return sorted(pairs, key=lambda pair: len(pair[1]), reverse=True)


def format_corrections(corrections):
    """Return compact correction labels for debug traces."""
    labels = []

    for correction in corrections:
        label = f"{correction.source}->{correction.target}"

        if correction.count > 1:
            label = f"{label}x{correction.count}"

        labels.append(label)

    return labels


N8N_STT_ALIASES = list(dict.fromkeys(list(N8N_STT_ALIASES) + ["nan", "NAN", "n8", "N8"]))
WORKFLOW_STT_ALIASES = ["walk flo", "work flo", "walk flow", "work flow", "워크 플로우"]
SYSTEM_ECHO_STT_ALIASES = [
    "\uc2dc\uc2a4\ud15c\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c\uc810\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c\uc9ec\uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc810 \uc5d0\ucf54",
    "\uc2dc\uc2a4\ud15c \uc9ec \uc5d0\ucf54",
    "system echo",
]

# Final STT alias overrides kept ASCII-safe for the Windows console code page.
N8N_STT_ALIASES = list(
    dict.fromkeys(
        list(N8N_STT_ALIASES)
        + [
            "nan",
            "NAN",
            "n8",
            "N8",
            "\uc5d4\ud654\ub97c",
            "\uc5d4\ud654\ub294",
            "\uc5d4\ud654",
        ]
    )
)
SYSTEM_ECHO_STT_ALIASES = list(
    dict.fromkeys(
        list(SYSTEM_ECHO_STT_ALIASES)
        + [
            "\uc2dc\uc2a4\ud15c\ub9e5\ud3ec",
            "\uc2dc\uc2a4\ud15c \ub9e5\ud3ec",
            "\uc2dc\uc2a4\ud15c\ud558\uace0",
            "\uc2dc\uc2a4\ud15c \ud558\uace0",
            "\uc2dc\uc2a4\ud15c4",
            "\uc2dc\uc2a4\ud15c 4",
        ]
    )
)
