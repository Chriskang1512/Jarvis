# Jarvis Runtime Motion Design Guideline

Status: v1.7 GUI roadmap contract

Runtime motion, color and sound are presentations of the shared
`RuntimeState`; they must never create a UI-only execution state. Motion should
communicate the current phase without competing with Goal content. Runtime
sounds are subtle transition cues, play once per state change, and always have
a persistent mute control.

| RuntimeState | Motion | Color | Duration | Sound cue |
| --- | --- | --- | --- | --- |
| Idle | Slow pulse | Gray | 3.0s | None |
| Listening | Expanding ring | Blue | 1.2s | Soft single chime |
| Thinking | Rotating ring | Purple | 1.0s | None |
| Planning | Rotating ring | Purple | 0.8s | None |
| Executing | Fast orbit | Green | 0.6s | None |
| Speaking | Soft pulse | Cyan | 1.0s | None |
| WaitingPermission | Blink | Orange | 0.8s | Gentle two-note chime |
| Completed | Single sweep, then settle | Cyan | 1.2s | Short high confirmation |
| Failed | Shake and fade | Red | 0.6s | Short low warning tone |

## Accessibility and operating rules

- Respect `prefers-reduced-motion`; functional status must remain legible when
  animation is disabled.
- Never communicate status by color alone. Always pair color with text and an
  icon or shape.
- Sound volume remains deliberately low and must not repeat during ordinary
  projection rerenders.
- Browser sound starts only after user interaction. Initial page load is silent.
- A user can disable sound independently of voice TTS, and the preference is
  retained locally.
- Failed and permission states should attract attention without becoming a
  continuous alarm.
- Rive, Dashboard, Wallpaper and Mobile clients must consume the same state
  names, semantic colors and timing intent.
