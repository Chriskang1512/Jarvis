"""Per-device Wake calibration models, derivation, and storage."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


CALIBRATION_VERSION = 2
DEFAULT_WAKE_CALIBRATION_PATH = Path("data") / "wake_calibration.json"


@dataclass(frozen=True)
class AudioFeature:
    peak: float
    rms: float
    crest: float


@dataclass(frozen=True)
class WakeCalibrationProfile:
    version: int
    created_at: str
    sample_count: int
    noise_floor_peak: float
    noise_floor_rms: float
    clap_peak_threshold: float
    clap_rms_threshold: float
    clap_crest_factor_threshold: float
    device_id: str = "default"
    clap_second_threshold_ratio: float = 0.55
    clap_release_threshold_ratio: float = 0.35
    clap_noise_floor_multiplier: float = 4.0

    def to_dict(self):
        return asdict(self)

    def wake_overrides(self):
        return {
            key: value
            for key, value in self.to_dict().items()
            if key.startswith("clap_") and key not in {"clap_count"}
        }


def derive_wake_calibration(noise_features, clap_features, device_id="default"):
    noise = tuple(noise_features)
    claps = tuple(clap_features)
    if len(noise) < 10:
        raise ValueError("CALIBRATION_NOISE_SAMPLE_REQUIRED")
    if len(claps) < 8:
        raise ValueError("CALIBRATION_CLAP_SAMPLE_REQUIRED")

    noise_peak = percentile([item.peak for item in noise], 0.95)
    noise_rms = percentile([item.rms for item in noise], 0.95)
    clap_peak_low = percentile([item.peak for item in claps], 0.20)
    clap_rms_low = percentile([item.rms for item in claps], 0.20)
    clap_crest_low = percentile([item.crest for item in claps], 0.20)
    peak_threshold = max(noise_peak * 3.0, clap_peak_low * 0.72, 0.05)
    rms_threshold = max(noise_rms * 3.0, clap_rms_low * 0.72, 0.008)
    if peak_threshold >= clap_peak_low or rms_threshold >= clap_rms_low:
        raise ValueError("CALIBRATION_SIGNAL_SEPARATION_INSUFFICIENT")

    return WakeCalibrationProfile(
        version=CALIBRATION_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        sample_count=len(claps),
        noise_floor_peak=round(noise_peak, 6),
        noise_floor_rms=round(noise_rms, 6),
        clap_peak_threshold=round(peak_threshold, 6),
        clap_rms_threshold=round(rms_threshold, 6),
        clap_crest_factor_threshold=round(max(3.0, clap_crest_low * 0.60), 4),
        device_id=str(device_id or "default"),
    )


def save_wake_calibration(profile, path=DEFAULT_WAKE_CALIBRATION_PATH):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def load_wake_calibration(path=DEFAULT_WAKE_CALIBRATION_PATH):
    target = Path(path)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    if int(payload.get("version", 0)) != CALIBRATION_VERSION:
        return None
    return WakeCalibrationProfile(**payload)


def percentile(values, ratio):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * float(ratio))))
    return ordered[index]
