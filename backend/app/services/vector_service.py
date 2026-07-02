"""Lightweight in-memory chunk store with TF-IDF-style keyword ranking.

No heavy ML model downloads — instant startup, perfect for demos.
Swap to ChromaDB + embeddings for production later.
"""

import math
import os
import re
from collections import OrderedDict

# Bound how many documents' chunks are held in RAM at once. The chunk index is
# just a cache: on a miss, the Q&A route rebuilds it from the persisted
# raw_text (see routes/qa.py), so evicting the least-recently-used document is
# safe and keeps memory flat no matter how many podcasts have been created.
_MAX_DOCS = int(os.getenv("CHUNK_CACHE_MAX_DOCS", "32"))

# LRU cache: most-recently-used doc at the end.
_store: "OrderedDict[str, list[str]]" = OrderedDict()


def store_chunks(doc_id: str, chunks: list[str]):
    """Cache a document's chunks in memory, evicting the least-recently-used."""
    if doc_id in _store:
        _store.move_to_end(doc_id)
    _store[doc_id] = chunks
    while len(_store) > _MAX_DOCS:
        _store.popitem(last=False)


def delete_chunks(doc_id: str):
    """Remove document chunks from memory (best-effort)."""
    _store.pop(doc_id, None)


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())


def query_chunks(query: str, doc_id: str, top_k: int = 5) -> list[str]:
    """Retrieve the most relevant chunks using simple keyword scoring."""
    chunks = _store.get(doc_id)
    if not chunks:
        return []
    _store.move_to_end(doc_id)  # mark as recently used

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
