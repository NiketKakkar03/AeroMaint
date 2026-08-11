"""Deterministic, dependency-free hybrid retrieval for approved engineering text."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+")


def _tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def _embedding(text: str, dimensions: int = 96) -> tuple[float, ...]:
    """Return a stable signed feature-hash embedding suitable for local/offline use."""
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        vector[index] += 1.0 if digest[2] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


@dataclass(frozen=True, slots=True)
class Document:
    source_url: str
    title: str
    version: str
    text: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    source_url: str
    title: str
    version: str
    page: int | None
    section: str
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    status: str
    query: str
    index_version: str
    results: tuple[dict[str, Any], ...]
    reason: str | None = None


class HybridIndex:
    def __init__(self, version: str, chunks: tuple[Chunk, ...]) -> None:
        self.version = version
        self.chunks = chunks

    def search(self, query: str, *, limit: int = 5, minimum_score: float = 0.015) -> SearchResult:
        query_terms = _tokens(query)
        if not query_terms:
            return SearchResult("insufficient_evidence", query, self.version, (), "empty query")
        query_embedding = _embedding(query)
        lexical: list[tuple[float, Chunk]] = []
        semantic: list[tuple[float, Chunk]] = []
        for chunk in self.chunks:
            terms = _tokens(chunk.text)
            frequencies = sum(terms.count(term) for term in query_terms)
            lexical.append((frequencies / max(1, len(terms)), chunk))
            semantic.append(
                (sum(a * b for a, b in zip(query_embedding, chunk.embedding, strict=True)), chunk)
            )
        lexical.sort(key=lambda item: (-item[0], item[1].chunk_id))
        semantic.sort(key=lambda item: (-item[0], item[1].chunk_id))
        scores: dict[str, float] = {}
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        for ranking in (lexical, semantic):
            for rank, (raw_score, chunk) in enumerate(ranking, start=1):
                if raw_score > 0:
                    scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1 / (60 + rank)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        if not ranked or ranked[0][1] < minimum_score:
            return SearchResult(
                "insufficient_evidence", query, self.version, (), "no approved source met threshold"
            )
        results = tuple(
            {
                "score": round(score, 6),
                "text": by_id[chunk_id].text,
                "citation": {
                    "chunk_id": chunk_id,
                    "source_url": by_id[chunk_id].source_url,
                    "title": by_id[chunk_id].title,
                    "version": by_id[chunk_id].version,
                    "page": by_id[chunk_id].page,
                    "section": by_id[chunk_id].section,
                },
            }
            for chunk_id, score in ranked
        )
        return SearchResult("ok", query, self.version, results)

    def write(self, destination: Path) -> None:
        payload = {"version": self.version, "chunks": [asdict(chunk) for chunk in self.chunks]}
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if not destination.exists() or destination.read_text() != encoded:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(encoded)

    @classmethod
    def read(cls, source: Path) -> HybridIndex:
        payload = json.loads(source.read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get("chunks"), list):
            raise ValueError("corrupt retrieval index")
        chunks = tuple(
            Chunk(**{**item, "embedding": tuple(item["embedding"])}) for item in payload["chunks"]
        )
        return cls(str(payload["version"]), chunks)


def build_index(documents: list[Document], *, words_per_chunk: int = 120) -> HybridIndex:
    chunks: list[Chunk] = []
    for document in sorted(documents, key=lambda item: (item.source_url, item.version)):
        if not document.source_url.startswith("https://") or not document.version.strip():
            raise ValueError("documents require an HTTPS source URL and explicit version")
        section = "Document"
        buffer: list[str] = []
        sections: list[tuple[str, str]] = []
        for line in document.text.splitlines():
            if line.startswith("#"):
                if buffer:
                    sections.append((section, " ".join(buffer)))
                    buffer = []
                section = line.lstrip("# ").strip() or "Document"
            elif line.strip():
                buffer.extend(line.split())
                while len(buffer) >= words_per_chunk:
                    sections.append((section, " ".join(buffer[:words_per_chunk])))
                    buffer = buffer[words_per_chunk:]
        if buffer:
            sections.append((section, " ".join(buffer)))
        for position, (heading, text) in enumerate(sections):
            identity = "|".join(
                (
                    document.source_url,
                    document.version,
                    str(document.page),
                    heading,
                    str(position),
                    text,
                )
            )
            chunks.append(
                Chunk(
                    hashlib.sha256(identity.encode()).hexdigest()[:20],
                    document.source_url,
                    document.title,
                    document.version,
                    document.page,
                    heading,
                    text,
                    _embedding(text),
                )
            )
    version_payload = "|".join(chunk.chunk_id for chunk in chunks)
    return HybridIndex(hashlib.sha256(version_payload.encode()).hexdigest()[:16], tuple(chunks))
