# 0010 - Creator Capability Alpha

## Status

Accepted

## Context

Japanese and Finance proved that language and calculation capabilities can plug
into Jarvis without changing Brain. Sprint 5 introduces the first creative
capability.

Creator should be a reusable creative engine, not a YouTube-only utility.

## Decision

Implement Creator Capability Alpha inside `jarvis.capabilities.creator`.

The capability follows the small application structure:

```text
creator/
  __init__.py
  metadata.py
  song/
  video/
  blog/
  presentation/
  tools/
    lyrics.py
    music_prompt.py
    title.py
    description.py
    song_package.py
  prompts/
    lyrics/
    music/
    thumbnail/
    script/
  tests/
```

The capability owns five SAFE tools:

- `creator_lyrics`
- `creator_music_prompt`
- `creator_title`
- `creator_description`
- `creator_song_package`

Every tool returns a structured output contract so future orchestration can
compose creative assets reliably.

Creator output contracts include project and asset identity:

```json
{
  "project": "jarvis_theme_song",
  "subdomain": "song",
  "asset": "lyrics"
}
```

Song is the first implemented sub-domain. Video, Blog, and Presentation are
reserved as future Creator sub-domains.

`creator_song_package` may call Creator tools sequentially inside the Creator
capability. It must not become the general Multi Tool Planner and must not
perform cross-capability orchestration.

## Consequences

- Jarvis now has three independent capability applications: Japanese, Finance,
  and Creator.
- Prompts are treated as Creator product assets.
- No Suno, Udio, YouTube, publishing, or planner integration is implemented in
  this sprint.
- Cross-capability creative workflows remain future v0.4 beta planner work.
