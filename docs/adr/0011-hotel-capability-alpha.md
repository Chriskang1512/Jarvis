# 0011 - Hotel Capability Alpha

## Status

Accepted

## Context

Jarvis v0.4 now has Japanese, Finance, and Creator capabilities. The next
capability should reflect real hospitality operations while preserving the Core
architecture.

Hotel workflows are useful because they produce operational artifacts: schedules,
complaint reports, and SOP guidance.

## Decision

Implement Hotel Capability Alpha inside `jarvis.capabilities.hotel`.

The capability follows the small application structure:

```text
hotel/
  __init__.py
  metadata.py
  tools/
    schedule_planner.py
    complaint_report.py
    complaint_manual.py
  prompts/
    schedule/
    complaint_report/
    complaint_manual/
  tests/
```

The capability owns three SAFE tools:

- `hotel_schedule_planner`
- `hotel_complaint_report`
- `hotel_complaint_manual`

Schedule planning is alpha-grade. It returns a draft, detected conflicts, and
unresolved constraints. It is not a perfect optimizer and does not make HR or
labor-law decisions.

## Consequences

- Jarvis now has four independent capability applications: Japanese, Finance,
  Creator, and Hotel.
- Hotel plugs into the same Capability -> ToolRegistry -> BrainToolRouter ->
  PermissionLayer -> Dispatcher path.
- No Excel export, Google Calendar integration, labor-law judgment, or automatic
  HR decision-making is implemented in this sprint.
