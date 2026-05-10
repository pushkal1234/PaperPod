"""Lightweight in-memory chunk store with TF-IDF-style keyword ranking.

No heavy ML model downloads — instant startup, perfect for demos.
Swap to ChromaDB + embeddings for production later.
"""

import math
import re
from collections import defaultdict

_store: dict[str, list[str]] = {}


def store_chunks(doc_id: str, chunks: list[str]):
    """Store document chunks in memory."""
    _store[doc_id] = chunks


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())


def query_chunks(query: str, doc_id: str, top_k: int = 5) -> list[str]:
    """Retrieve the most relevant chunks using simple keyword scoring."""
    chunks = _store.get(doc_id, [])
    if not chunks:
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return chunks[:top_k]

    scored = []
    for chunk in chunks:
        chunk_tokens = _tokenize(chunk)
        if not chunk_tokens:
            scored.append((0, chunk))
            continue
        chunk_token_set = set(chunk_tokens)
        overlap = query_tokens & chunk_token_set
        score = len(overlap) / (1 + math.log(1 + len(chunk_tokens)))
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
