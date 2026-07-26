# Wake And Input Hardening

Run these probes from the repository root in a quiet room. Each command opens
the microphone only for the requested duration. It does not call STT, Planner,
LLM, or TTS and does not store audio.

## Automated Regression

```powershell
python -m unittest tests.test_input_wake_manager tests.test_tts_providers -q
```

This covers detector rules, Wake Provider priority, shared-monitor lifecycle,
hotkey matching contracts, external trigger contracts, and keyboard-level VAD
rejection.

## Live Clap And False-positive Matrix

Perform only the sound named by `--label` after `READY` appears.

```powershell
python scripts\wake_hardening_probe.py --label single-clap --duration 4 --expected 0 --require-state FIRST_CLAP
python scripts\wake_hardening_probe.py --label double-clap --duration 4 --expected 1 --require-state CONFIRMED
python scripts\wake_hardening_probe.py --label triple-clap --duration 4 --expected 0 --require-state TRIPLE_CANCELLED
python scripts\wake_hardening_probe.py --label keyboard-typing --duration 8 --expected 0
python scripts\wake_hardening_probe.py --label desk-impact --duration 5 --expected 0
python scripts\wake_hardening_probe.py --label door-close --duration 5 --expected 0
python scripts\wake_hardening_probe.py --label music-video --duration 15 --expected 0
```

Repeat the double-clap probe with a fast, normal, and slow pair. The supported
interval is printed by the probe. Tune thresholds only after retaining the
`RESULT` lines for all cases; improving one case must not regress another.
Clap cases pass only when their required detector state is observed. This
prevents a triple-clap test with inaudible claps from being reported as a
successful rejection. Candidate timestamps and gaps help distinguish a real
second clap from two adjacent microphone frames produced by one clap.
Detector output also includes `first_clap_at`, `second_clap_at`, `gap`, and
`rejection_reason`. Tune the interval only after repeated results identify
`gap_above_max`; `refractory` usually means adjacent frames from one impulse.
Keep the first-clap baseline at peak `0.55`, RMS `0.08`, and crest factor `3.0`.
Any adaptive sensitivity change must remain limited to an active pending pair
and must be compared against the full environmental false-positive matrix.

The first post-fix baseline measured 2/11 confirmations with zero exceptions:
four trials had no candidate and five accepted only the first clap. The first
clap retains the strict baseline. During its bounded 0.8-second pending window,
the second clap uses `clap_second_threshold_ratio=0.65` to tolerate microphone
AGC attenuation without allowing a weak sound to start a clap sequence.

The adaptive threshold is experimental and is armed only after all of these
conditions hold:

- the strict first clap was accepted;
- the refractory interval elapsed;
- peak and RMS returned below the release threshold;
- the second candidate still passes the original crest-factor requirement;
- its RMS exceeds both the adaptive threshold and four times recent noise.

Trace exposes first/second thresholds, refractory elapsed time, release state,
second-candidate reason, and cumulative activation count. Final approval
requires 9/10 Double Clap success plus zero activation across repeated Single
Clap, Triple Clap, keyboard, desk, door, and media tests.

## Full Runtime Checks

1. Start `start_jarvis.ps1` and confirm `WAKE_LISTENING monitor=ON`.
2. Wake once by double clap and confirm `ACTIVATED monitor=OFF`.
3. Finish or cancel the conversation and confirm the next
   `WAKE_LISTENING monitor=ON`.
4. Confirm every command and follow-up emits `voice.input.envelope`.
5. Verify Trace contains activation type/provider, stage, turn type, content
   length, and fingerprint, but no raw content.

## Current Adapter Boundary

`KeyboardWakeProvider` and `TouchPortalWakeProvider` currently implement the
provider and queue contracts only. There is no live Windows global-hotkey
adapter or Touch Portal transport adapter yet. Their unit tests can pass, but
live checklist items remain pending until those adapters are implemented.
