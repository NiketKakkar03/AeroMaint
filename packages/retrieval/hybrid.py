"""Deterministic hybrid retrieval with citation-preserving chunks.

The local profile deliberately has no model download: a hashed word/character embedding is
reproducible offline.  Production can persist the same vectors in pgvector.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]*")
CONCEPTS = {
    "authorization": "approved authorized approval",
    "authorize": "approved authorized approval",
    "remaining": "remaining residual",
    "residual": "remaining residual",
    "failure": "degradation damage failure",
    "fault": "degradation damage failure",
    "prediction": "prognostics forecast prediction",
    "forecast": "prognostics forecast prediction",
}


def _tokens(text: str) -> list[str]:
    tokens = TOKEN.findall(text.lower())
    return [alias for token in tokens for alias in CONCEPTS.get(token, token).split()]


def local_embedding(text: str, dimensions: int = 96) -> tuple[float, ...]:
    """Stable feature-hash embedding suitable for the zero-cost/offline profile."""
    vector = [0.0] * dimensions
    normalized = " ".join(_tokens(text))
    features = normalized.split() + [normalized[i : i + 3] for i in range(len(normalized) - 2)]
    for feature in features:
        digest = hashlib.sha256(feature.encode()).digest()
        vector[int.from_bytes(digest[:2], "big") % dimensions] += 1.0 if digest[2] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


@dataclass(frozen=True, slots=True)
class Document:
    source_url: str
    title: str
    version: str
    text: str
    page: int | None = None
    checksum: str = ""


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    source_url: str
    title: str
    version: str
    page: int | None
    section: str
    text: str
    start_char: int
    end_char: int
    checksum: str
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
        query_embedding = local_embedding(query)
        lexical: list[tuple[float, Chunk]] = []
        semantic: list[tuple[float, Chunk]] = []
        query_counts = Counter(query_terms)
        for chunk in self.chunks:
            terms = _tokens(f"{chunk.section} {chunk.text}")
            counts = Counter(terms)
            lexical_score = sum(min(counts[t], count) for t, count in query_counts.items())
            lexical.append((lexical_score / math.sqrt(max(1, len(terms))), chunk))
            semantic.append(
                (sum(a * b for a, b in zip(query_embedding, chunk.embedding, strict=True)), chunk)
            )
        lexical.sort(key=lambda item: (-item[0], item[1].chunk_id))
        semantic.sort(key=lambda item: (-item[0], item[1].chunk_id))
        scores: dict[str, float] = {}
        lexical_evidence = {chunk.chunk_id: score for score, chunk in lexical}
        semantic_evidence = {chunk.chunk_id: score for score, chunk in semantic}
        for weight, ranking in ((1.15, lexical), (1.0, semantic)):
            for rank, (raw_score, chunk) in enumerate(ranking, start=1):
                if raw_score > 0:
                    scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + weight / (60 + rank)
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        ranked = [
            (chunk_id, score)
            for chunk_id, score in ranked
            if lexical_evidence[chunk_id] > 0 or semantic_evidence[chunk_id] >= 0.25
        ][:limit]
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
                    "start_char": by_id[chunk_id].start_char,
                    "end_char": by_id[chunk_id].end_char,
                    "checksum": by_id[chunk_id].checksum,
                },
            }
            for chunk_id, score in ranked
        )
        return SearchResult("ok", query, self.version, results)

    def write(self, destination: Path) -> bool:
        """Atomically write only a changed index; return whether publication occurred."""
        payload = {
            "schema_version": "2.0.0",
            "version": self.version,
            "chunks": [asdict(c) for c in self.chunks],
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if destination.exists() and destination.read_text() == encoded:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(encoded)
        temporary.replace(destination)
        return True

    @classmethod
    def read(cls, source: Path) -> HybridIndex:
        try:
            payload = json.loads(source.read_text())
            if payload.get("schema_version") != "2.0.0" or not isinstance(payload["chunks"], list):
                raise ValueError
            chunks = tuple(
                Chunk(**{**item, "embedding": tuple(item["embedding"])})
                for item in payload["chunks"]
            )
            if any(c.end_char - c.start_char != len(c.text) or c.start_char < 0 for c in chunks):
                raise ValueError
            expected = _index_version(chunks)
            if payload.get("version") != expected:
                raise ValueError
            return cls(expected, chunks)
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("corrupt retrieval index") from exc


def _index_version(chunks: tuple[Chunk, ...]) -> str:
    return hashlib.sha256("|".join(chunk.chunk_id for chunk in chunks).encode()).hexdigest()[:16]


def build_index(documents: list[Document], *, words_per_chunk: int = 120) -> HybridIndex:
    if words_per_chunk < 1:
        raise ValueError("words_per_chunk must be positive")
    chunks: list[Chunk] = []
    for document in sorted(
        documents, key=lambda item: (item.source_url, item.version, item.page or 0)
    ):
        if not document.source_url.startswith("https://") or not document.version.strip():
            raise ValueError("documents require an HTTPS source URL and explicit version")
        checksum = document.checksum or hashlib.sha256(document.text.encode()).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("documents require a SHA-256 checksum")
        section = "Document"
        spans: list[tuple[int, int]] = []

        def emit(
            grouped_spans: list[tuple[int, int]],
            heading: str,
            source_document: Document = document,
            source_checksum: str = checksum,
        ) -> None:
            for offset in range(0, len(grouped_spans), words_per_chunk):
                group = grouped_spans[offset : offset + words_per_chunk]
                start, end = group[0][0], group[-1][1]
                text = source_document.text[start:end]
                identity = "|".join(
                    (
                        source_document.source_url,
                        source_document.version,
                        source_checksum,
                        str(source_document.page),
                        heading,
                        str(start),
                        str(end),
                    )
                )
                chunks.append(
                    Chunk(
                        hashlib.sha256(identity.encode()).hexdigest()[:20],
                        source_document.source_url,
                        source_document.title,
                        source_document.version,
                        source_document.page,
                        heading,
                        text,
                        start,
                        end,
                        source_checksum,
                        local_embedding(f"{heading} {text}"),
                    )
                )

        position = 0
        for line in document.text.splitlines(keepends=True):
            if line.lstrip().startswith("#"):
                if spans:
                    emit(spans, section)
                spans = []
                section = line.lstrip("# ").strip() or "Document"
            else:
                spans.extend(
                    (position + m.start(), position + m.end()) for m in re.finditer(r"\S+", line)
                )
            position += len(line)
        if spans:
            emit(spans, section)
    ordered = tuple(sorted(chunks, key=lambda c: c.chunk_id))
    return HybridIndex(_index_version(ordered), ordered)
