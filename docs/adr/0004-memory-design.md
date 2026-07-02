# 0004 - Memory Design

## Status

Accepted

## Context

Jarvis needs a simple Memory system that beginners can understand.

The first version should store notes locally without adding a database too early.

## Decision

Memory will start with a simple text file stored at `data/memory.txt`.

The file stores notes with a timestamp and plain text content.

## Consequences

- The Memory system is easy to inspect and debug.
- No external database is required for early development.
- The storage layer can later be replaced by a database if needed.

## Notes

`data/*.txt` must stay in `.gitignore` because it can contain personal information.
