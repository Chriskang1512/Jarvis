import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis.config.loader import ConfigurationLoader
from jarvis.wake import (
    AudioFeature,
    derive_wake_calibration,
    load_wake_calibration,
    save_wake_calibration,
)
from scripts.wake_calibration import collect_trial


class TestWakeCalibration(unittest.TestCase):
    @patch("scripts.wake_calibration.input", return_value="")
    @patch("scripts.wake_calibration.capture_features")
    def test_calibration_trial_retries_until_exactly_two_claps(
        self,
        capture_features,
        _input,
    ):
        feature = AudioFeature(0.30, 0.05, 6.0)
        capture_features.side_effect = [
            [(0.1, feature)],
            [(0.1, feature), (0.4, feature)],
        ]

        candidates = collect_trial(
            trial=1,
            trial_count=5,
            max_attempts=3,
            duration=3.0,
            device=None,
            noise_peak=0.001,
            noise_rms=0.001,
        )

        self.assertEqual(candidates, [feature, feature])
        self.assertEqual(capture_features.call_count, 2)

    @patch("scripts.wake_calibration.input", return_value="")
    @patch("scripts.wake_calibration.capture_features")
    def test_calibration_trial_fails_after_incomplete_attempts(
        self,
        capture_features,
        _input,
    ):
        feature = AudioFeature(0.30, 0.05, 6.0)
        capture_features.return_value = [(0.1, feature)]

        candidates = collect_trial(
            trial=1,
            trial_count=5,
            max_attempts=2,
            duration=3.0,
            device=None,
            noise_peak=0.001,
            noise_rms=0.001,
        )

        self.assertIsNone(candidates)
        self.assertEqual(capture_features.call_count, 2)

    def test_derives_profile_between_noise_and_natural_claps(self):
        noise = [AudioFeature(0.01, 0.003, 3.3) for _ in range(20)]
        claps = [AudioFeature(0.30 + index * 0.02, 0.05, 6.0) for index in range(10)]

        profile = derive_wake_calibration(noise, claps, device_id="reference-mic")

        self.assertEqual(profile.sample_count, 10)
        self.assertEqual(profile.device_id, "reference-mic")
        self.assertEqual(profile.clap_second_threshold_ratio, 0.55)
        self.assertGreater(profile.clap_peak_threshold, profile.noise_floor_peak)
        self.assertLess(profile.clap_peak_threshold, 0.30)
        self.assertGreater(profile.clap_rms_threshold, profile.noise_floor_rms)
        self.assertLess(profile.clap_rms_threshold, 0.05)

    def test_rejects_insufficient_signal_separation(self):
        noise = [AudioFeature(0.20, 0.04, 5.0) for _ in range(20)]
        claps = [AudioFeature(0.21, 0.041, 5.1) for _ in range(10)]

        with self.assertRaisesRegex(
            ValueError,
            "CALIBRATION_SIGNAL_SEPARATION_INSUFFICIENT",
        ):
            derive_wake_calibration(noise, claps)

    def test_profile_store_is_restorable_and_overlays_runtime_wake_config(self):
        noise = [AudioFeature(0.01, 0.003, 3.3) for _ in range(20)]
        claps = [AudioFeature(0.40, 0.06, 6.0) for _ in range(10)]
        profile = derive_wake_calibration(noise, claps)

        root = Path("tests") / "_wake_calibration_test"
        root.mkdir(exist_ok=True)
        try:
            config_path = root / "config.json"
            profile_path = root / "wake.json"
            config_path.write_text(
                json.dumps({"wake": {"clap_peak_threshold": 0.90}}),
                encoding="utf-8",
            )
            save_wake_calibration(profile, profile_path)

            restored = load_wake_calibration(profile_path)
            config = ConfigurationLoader(
                config_path,
                wake_calibration_path=profile_path,
            ).load()
            self.assertFalse(profile_path.with_suffix(".json.tmp").exists())
        finally:
            for child in root.iterdir():
                child.unlink()
            root.rmdir()

        self.assertEqual(restored, profile)
        self.assertEqual(config.wake.clap_peak_threshold, profile.clap_peak_threshold)

    def test_profile_for_other_device_is_not_applied(self):
        noise = [AudioFeature(0.01, 0.003, 3.3) for _ in range(20)]
        claps = [AudioFeature(0.40, 0.06, 6.0) for _ in range(10)]
        profile = derive_wake_calibration(noise, claps, device_id="other-mic")
        root = Path("tests") / "_wake_calibration_device_test"
        root.mkdir(exist_ok=True)
        try:
            config_path = root / "config.json"
            profile_path = root / "wake.json"
            config_path.write_text(
                json.dumps(
                    {
                        "stt": {"device": "default"},
                        "wake": {"clap_peak_threshold": 0.90},
                    }
                ),
                encoding="utf-8",
            )
            save_wake_calibration(profile, profile_path)

            config = ConfigurationLoader(
                config_path,
                wake_calibration_path=profile_path,
            ).load()
        finally:
            for child in root.iterdir():
                child.unlink()
            root.rmdir()

        self.assertEqual(config.wake.clap_peak_threshold, 0.90)


if __name__ == "__main__":
    unittest.main()
