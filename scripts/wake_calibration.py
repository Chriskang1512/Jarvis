"""Interactive five-trial Wake calibration wizard."""

import argparse
from math import sqrt
from pathlib import Path
import sys
from time import monotonic, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import ConfigurationLoader
from jarvis.wake import AudioFeature, derive_wake_calibration, save_wake_calibration


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--noise-seconds", type=float, default=3.0)
    parser.add_argument("--clap-seconds", type=float, default=3.0)
    parser.add_argument("--output", default="data/wake_calibration.json")
    return parser.parse_args()


def main():
    args = parse_args()
    config = ConfigurationLoader(wake_calibration_path="").load()
    device = None if config.stt.device == "default" else config.stt.device

    input("Press Enter, then stay quiet for the noise sample...")
    noise_frames = capture_features(args.noise_seconds, device=device)
    noise_peak = percentile([item.peak for _, item in noise_frames], 0.95)
    noise_rms = percentile([item.rms for _, item in noise_frames], 0.95)
    print(f"[Calibration] noise peak95={noise_peak:.4f} rms95={noise_rms:.4f}")

    clap_features = []
    for trial in range(1, max(1, args.trials) + 1):
        input(f"Trial {trial}/{args.trials}: Press Enter, then clap twice naturally...")
        frames = capture_features(args.clap_seconds, device=device)
        candidates = extract_trial_claps(frames, noise_peak, noise_rms)
        print(
            f"[Calibration] trial={trial} detected={len(candidates)} "
            f"features={format_features(candidates)}"
        )
        clap_features.extend(candidates[:2])

    try:
        profile = derive_wake_calibration(
            [feature for _, feature in noise_frames],
            clap_features,
            device_id=str(config.stt.device),
        )
    except ValueError as error:
        print(f"[Calibration] FAILED reason={error}")
        print("[Calibration] No profile was written.")
        raise SystemExit(1)

    target = save_wake_calibration(profile, args.output)
    print(
        "[Calibration] PASS "
        f"samples={profile.sample_count} "
        f"peak={profile.clap_peak_threshold:.4f} "
        f"rms={profile.clap_rms_threshold:.4f} "
        f"crest={profile.clap_crest_factor_threshold:.2f}"
    )
    print(f"[Calibration] profile={target}")


def capture_features(duration, device=None):
    try:
        import sounddevice
    except ImportError as exc:
        raise SystemExit("sounddevice is required for calibration") from exc

    frames = []
    started_at = monotonic()

    def callback(indata, frame_count, time_info, status):
        del frame_count, time_info
        if status:
            print(f"[Calibration] audio_status={status}")
        values = tuple(float(item[0]) for item in indata)
        if not values:
            return
        peak = max(abs(value) for value in values)
        rms = sqrt(sum(value * value for value in values) / len(values))
        crest = peak / max(rms, 1e-9)
        frames.append((monotonic() - started_at, AudioFeature(peak, rms, crest)))

    with sounddevice.InputStream(
        samplerate=16000,
        blocksize=800,
        device=device,
        channels=1,
        dtype="float32",
        callback=callback,
    ):
        sleep(max(0.1, float(duration)))
    return frames


def extract_trial_claps(frames, noise_peak, noise_rms):
    peak_floor = max(float(noise_peak) * 3.0, 0.05)
    rms_floor = max(float(noise_rms) * 3.0, 0.008)
    raw = [
        (timestamp, feature)
        for timestamp, feature in frames
        if feature.peak >= peak_floor
        and feature.rms >= rms_floor
        and feature.crest >= 3.0
    ]
    clusters = []
    for timestamp, feature in raw:
        if not clusters or timestamp - clusters[-1][-1][0] >= 0.10:
            clusters.append([(timestamp, feature)])
        else:
            clusters[-1].append((timestamp, feature))
    representatives = [
        max(cluster, key=lambda item: item[1].peak * item[1].rms)
        for cluster in clusters
    ]
    return [feature for _, feature in representatives]


def percentile(values, ratio):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def format_features(features):
    if not features:
        return "-"
    return ",".join(
        f"(peak={item.peak:.3f},rms={item.rms:.3f},crest={item.crest:.2f})"
        for item in features
    )


if __name__ == "__main__":
    main()
