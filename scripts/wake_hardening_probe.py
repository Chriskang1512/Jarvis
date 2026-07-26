"""Measure live microphone wake behavior without starting STT or Planner."""

import argparse
from math import sqrt
from pathlib import Path
import sys
from time import monotonic, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.config import ConfigurationLoader
from jarvis.wake import ClapDetector, ClapDetectorSettings


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Name printed in the result")
    parser.add_argument("--duration", type=float, default=5.0, help="Capture seconds")
    parser.add_argument(
        "--expected",
        type=int,
        required=True,
        help="Expected confirmed double-clap activations",
    )
    parser.add_argument(
        "--require-state",
        action="append",
        default=[],
        help="Detector state that must be observed; may be repeated",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = ConfigurationLoader().load()
    settings = ClapDetectorSettings(
        peak_threshold=config.wake.clap_peak_threshold,
        rms_threshold=config.wake.clap_rms_threshold,
        crest_factor_threshold=config.wake.clap_crest_factor_threshold,
        min_gap_seconds=config.wake.clap_min_gap_seconds,
        max_gap_seconds=config.wake.clap_max_gap_seconds,
        settle_seconds=config.wake.clap_settle_seconds,
        second_clap_threshold_ratio=config.wake.clap_second_threshold_ratio,
    )
    detector = ClapDetector(settings)
    activations = 0
    candidate_count = 0
    max_peak = 0.0
    max_rms = 0.0
    max_crest = 0.0
    observed_states = []
    last_candidate_at = None
    capture_started_at = monotonic()

    try:
        import sounddevice
    except ImportError as exc:
        raise SystemExit("sounddevice is required for the live probe") from exc

    print(f"[Probe] label={args.label} duration={args.duration:.1f}s expected={args.expected}")
    print(
        "[Probe] thresholds "
        f"peak={settings.peak_threshold:.3f} "
        f"rms={settings.rms_threshold:.3f} "
        f"crest={settings.crest_factor_threshold:.2f} "
        f"gap={settings.min_gap_seconds:.2f}-{settings.max_gap_seconds:.2f}s "
        f"settle={settings.settle_seconds:.2f}s "
        f"second_ratio={settings.second_clap_threshold_ratio:.2f}"
    )
    print("[Probe] READY - perform the sound now")

    def on_audio(indata, frames, time_info, status):
        nonlocal activations, candidate_count, max_peak, max_rms, max_crest
        nonlocal last_candidate_at
        del frames, time_info
        if status:
            print(f"[Probe] audio_status={status}")
        samples = tuple(float(item[0]) for item in indata)
        if not samples:
            return
        peak = max(abs(sample) for sample in samples)
        rms = sqrt(sum(sample * sample for sample in samples) / len(samples))
        crest = peak / max(rms, 1e-9)
        max_peak = max(max_peak, peak)
        max_rms = max(max_rms, rms)
        max_crest = max(max_crest, crest)
        threshold_ratio = (
            settings.second_clap_threshold_ratio
            if detector.first_clap_at is not None and detector.second_clap_at is None
            else 1.0
        )
        if (
            peak >= settings.peak_threshold * threshold_ratio
            and rms >= settings.rms_threshold * threshold_ratio
            and crest >= settings.crest_factor_threshold
        ):
            candidate_count += 1
            candidate_at = monotonic()
            gap = (
                "-"
                if last_candidate_at is None
                else f"{candidate_at - last_candidate_at:.3f}s"
            )
            print(
                f"[Probe] candidate={candidate_count} "
                f"at={candidate_at - capture_started_at:.3f}s gap={gap} "
                f"peak={peak:.3f} rms={rms:.3f} crest={crest:.2f}"
            )
            last_candidate_at = candidate_at
        detected = detector.process(samples, monotonic())
        decision = detector.pop_decision()
        diagnostic = detector.pop_diagnostic()
        detector_state = decision or diagnostic.get("detector_state")
        if detector_state:
            observed_states.append(detector_state)
            first_at = diagnostic.get("first_clap_at")
            second_at = diagnostic.get("second_clap_at")
            gap_seconds = diagnostic.get("gap_seconds")
            print(
                f"[Probe] state={detector_state} "
                f"first_clap_at={format_relative_time(first_at, capture_started_at)} "
                f"second_clap_at={format_relative_time(second_at, capture_started_at)} "
                f"gap={'-' if gap_seconds is None else f'{gap_seconds:.3f}s'} "
                f"rejection_reason={diagnostic.get('rejection_reason') or '-'} "
                f"peak={peak:.3f} rms={rms:.3f} crest={crest:.2f}"
            )
        if detected:
            activations += 1

    device = None if config.stt.device == "default" else config.stt.device
    with sounddevice.InputStream(
        samplerate=16000,
        blocksize=800,
        device=device,
        channels=1,
        dtype="float32",
        callback=on_audio,
    ):
        sleep(max(0.1, args.duration))

    missing_states = [
        state for state in args.require_state if state not in observed_states
    ]
    passed = activations == args.expected and not missing_states
    print(
        f"[Probe] RESULT={'PASS' if passed else 'FAIL'} "
        f"label={args.label} activations={activations} expected={args.expected} "
        f"candidates={candidate_count} max_peak={max_peak:.3f} "
        f"max_rms={max_rms:.3f} max_crest={max_crest:.2f} "
        f"states={','.join(observed_states) or '-'} "
        f"missing_states={','.join(missing_states) or '-'}"
    )
    raise SystemExit(0 if passed else 1)


def format_relative_time(timestamp, started_at):
    if timestamp is None:
        return "-"
    return f"{float(timestamp) - float(started_at):.3f}s"


if __name__ == "__main__":
    main()
