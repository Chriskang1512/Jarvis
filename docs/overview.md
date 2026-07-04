# Jarvis Project Overview

Jarvis is a Python-based personal AI assistant project.

The first version is a local CLI chat program. The user types a command, the Brain analyzes it, and the Brain sends the command to a specialized Agent.

## Main Parts

- Brain: Main controller that decides what should happen.
- Brain Tool Router: Registry-driven router that chooses SAFE tools before LLM chat.
- Agents: Small workers that handle specialized jobs.
- Memory: Simple storage for conversation and task history.
- Config: Basic project settings.
- Logs: Place for future execution logs.
- Docs: Project notes and explanations.

## First Development Goal

The first goal is not to build every AI feature at once. The first goal is to create a clean structure that can grow safely.

## v0.4 Tool Routing

```text
User
  |
Voice / Text
  |
Brain
  |
Brain Tool Router
  |
  |--------------------|
  |                    |
Tool Route            LLM Route
  |                    |
Permission            Chat
  |
Dispatcher
  |
Tool
```

The router discovers tools from `ToolRegistry` and uses `ToolMetadata` to score
candidate routes. It does not execute tools directly. It only returns a
`ToolRequest`; the existing `PermissionLayer` and `ToolDispatcher` keep their
v0.3 responsibilities.

## v0.4 Capability Plugins

```text
Capability
  |
Tool
  |
Permission
  |
Dispatcher
```

Capabilities group related tools into independent extension modules. The
Capability Registry discovers enabled capabilities and registers their tools
into the shared Tool Registry. Brain remains unaware of individual capabilities.

## Japanese Capability Alpha

Japanese is the first concrete capability. It registers four SAFE tools:

- `japanese_translate`
- `japanese_grammar`
- `japanese_reply`
- `japanese_review`

These tools are normal ToolRegistry entries. Brain routes to them by metadata;
PermissionLayer and ToolDispatcher keep the same Core responsibilities.

Japanese also sets the internal structure pattern for larger capabilities:
metadata lives at capability level, tools live in separate modules, prompt
templates live under `prompts/`, and future capability-local tests can live
under `tests/`.

## Finance Capability Alpha

Finance is the second concrete capability. It registers four SAFE tools:

- `finance_compound`
- `finance_average_price`
- `finance_profit`
- `finance_exchange`
- `finance_portfolio`

Finance proves that a different domain can join the same platform without
modifying Brain, Router, Registry, Permission, or Dispatcher.

## Creator Capability Alpha

Creator is the third concrete capability and the first creative engine. It
registers five SAFE tools:

- `creator_lyrics`
- `creator_music_prompt`
- `creator_title`
- `creator_description`
- `creator_song_package`

Prompts are first-class assets under `prompts/`. Creator outputs are structured
so future planners can compose lyrics, music prompts, titles, descriptions, tags,
and thumbnail prompts without tool-specific parsing.

Creator is also the first capability designed with sub-domains. Song is active
now; Video, Blog, and Presentation are reserved. Creator assets carry
`project`, `subdomain`, and `asset` fields to support future Project -> Assets
-> Output workflows.

## Hotel Capability Alpha

Hotel is the fourth concrete capability and Jarvis's hospitality operations
assistant. It registers three SAFE tools:

- `hotel_schedule_planner`
- `hotel_complaint_report`
- `hotel_complaint_manual`

The schedule planner returns draft schedules, conflicts, and notes rather than a
perfect optimizer. Complaint tools return structured manager reports and SOP
guidance for front office workflows.
