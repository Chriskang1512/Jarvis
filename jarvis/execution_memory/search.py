"""Replaceable execution-memory indexing and search boundary."""

from __future__ import annotations

import re
from typing import Protocol

from .models import MemorySearchResult


class SemanticSearchProvider(Protocol):
    provider_name: str

    def search(self, query, records, limit=10): ...


class KeywordSemanticSearchProvider:
    provider_name = "keyword"

    def search(self, query, records, limit=10):
        query_tokens = tokenize(query)
        results = []
        for record in records:
            fields = {
                "goalSignature": record.goal_signature,
                "tags": " ".join(record.tags),
                "capabilities": " ".join(
                    item.capability_id for item in record.histories
                ),
                "outcome": record.outcome,
            }
            field_tokens = {
                key: tokenize(value) for key, value in fields.items()
            }
            overlap = set().union(*field_tokens.values()).intersection(
                query_tokens
            )
            score = (
                len(overlap) / max(1, len(query_tokens))
                if query_tokens
                else 1.0
            )
            if query_tokens and not overlap:
                continue
            matched = tuple(
                key
                for key, tokens in field_tokens.items()
                if tokens.intersection(query_tokens)
            )
            results.append(
                MemorySearchResult(
                    record,
                    score,
                    matched,
                    record.provenance,
                    record.confidence.verification_status,
                )
            )
        return sorted(
            results,
            key=lambda item: (item.score, item.record.created_at),
            reverse=True,
        )[: max(1, int(limit))]


class MemoryIndexer:
    def __init__(self, repository):
        self.repository = repository

    def index(self, record):
        return self.repository.add(record)


class MemorySearch:
    def __init__(self, repository, semantic_provider=None):
        self.repository = repository
        self.semantic_provider = (
            semantic_provider or KeywordSemanticSearchProvider()
        )

    def keyword(self, query="", *, history_types=(), limit=20):
        return self.repository.search_metadata(
            query, history_types=history_types, limit=limit
        )

    def semantic(self, query, *, limit=10):
        records = self.repository.list(limit=max(limit * 10, 100))
        return self.semantic_provider.search(query, records, limit=limit)


def tokenize(value):
    return {
        token
        for token in re.findall(
            r"[A-Za-z0-9가-힣_.-]+", str(value or "").casefold()
        )
        if token
    }
