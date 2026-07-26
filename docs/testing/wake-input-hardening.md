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
python scripts\wake_hardening_probe.py --label single-clap --duration 4 --expected 0
python scripts\wake_hardening_probe.py --label double-clap --duration 4 --expected 1
python scripts\wake_hardening_probe.py --label triple-clap --duration 4 --expected 0
python scripts\wake_hardening_probe.py --label keyboard-typing --duration 8 --expected 0
python scripts\wake_hardening_probe.py --label desk-impact --duration 5 --expected 0
python scripts\wake_hardening_probe.py --label door-close --duration 5 --expected 0
python scripts\wake_hardening_probe.py --label music-video --duration 15 --expected 0
```

Repeat the double-clap probe with a fast, normal, and slow pair. The supported
interval is printed by the probe. Tune thresholds only after retaining the
`RESULT` lines for all cases; improving one case must not regress another.

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
