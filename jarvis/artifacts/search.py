"""Metadata search plus a non-wired semantic search extension contract."""

from typing import Protocol

from .models import ArtifactSearchResult


class ArtifactSearchProvider(Protocol):
    provider_name: str

    def search(self, query, artifacts, limit=20): ...


class ArtifactIndexer:
    def __init__(self, repository):
        self.repository = repository

    def index(self, artifact):
        return self.repository.save(artifact)


class ArtifactSearch:
    def __init__(self, repository, semantic_provider=None):
        self.repository = repository
        self.semantic_provider = semantic_provider

    def metadata(self, **criteria):
        return self.repository.search_metadata(**criteria)

    def semantic(self, query, limit=20):
        if self.semantic_provider is None:
            raise RuntimeError("Artifact semantic search is not enabled.")
        return self.semantic_provider.search(query, self.repository.list(limit=1000), limit)


class KeywordArtifactSearchProvider:
    """Test/reference provider; not connected to the Runtime."""

    provider_name = "keyword-reference"

    def search(self, query, artifacts, limit=20):
        tokens = {item for item in str(query).casefold().split() if item}
        results = []
        for artifact in artifacts:
            fields = {
                "title": artifact.title.casefold(),
                "summary": artifact.summary.casefold(),
                "tags": " ".join(artifact.tags).casefold(),
            }
            matched = tuple(name for name, value in fields.items() if any(token in value for token in tokens))
            if matched:
                results.append(ArtifactSearchResult(artifact, len(matched) / len(fields), matched))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
