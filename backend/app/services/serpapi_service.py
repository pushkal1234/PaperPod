"""SerpAPI Google Search — web results combined with document context via Groq."""

import logging

import httpx

from app.config import settings
from app.services.llm_service import answer_question_hybrid

logger = logging.getLogger("paperpod")

SERPAPI_URL = "https://serpapi.com/search.json"
MAX_WEB_RESULTS = 5


def is_configured() -> bool:
    return bool(settings.SERPAPI_API_KEY.strip())


def search_web(query: str) -> list[dict]:
    """Run a Google search via SerpAPI. Returns [{title, link, snippet}, ...]."""
    if not is_configured():
        raise RuntimeError("SERPAPI_API_KEY is not configured")

    params = {
        "q": query,
        "api_key": settings.SERPAPI_API_KEY,
        "engine": "google",
        "num": MAX_WEB_RESULTS,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.get(SERPAPI_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if data.get("error"):
        raise RuntimeError(data["error"])

    results = []
    for item in data.get("organic_results", [])[:MAX_WEB_RESULTS]:
        link = item.get("link")
        if not link:
            continue
        results.append({
            "title": item.get("title") or link,
            "link": link,
            "snippet": item.get("snippet") or item.get("snippet_highlighted", [""])[0]
            if isinstance(item.get("snippet_highlighted"), list)
            else (item.get("snippet") or ""),
        })

    # Knowledge graph / answer box as extra context when present
    answer_box = data.get("answer_box") or {}
    if answer_box.get("answer") and len(results) < MAX_WEB_RESULTS:
        results.insert(0, {
            "title": answer_box.get("title") or "Featured answer",
            "link": answer_box.get("link") or answer_box.get("displayed_link") or "",
            "snippet": answer_box.get("answer") or answer_box.get("snippet", ""),
        })

    logger.info(f"[SerpAPI] {len(results)} results for query: {query[:80]}")
    return results


def answer_with_web_search(question: str, document_context: str) -> dict:
    """Search the web (SerpAPI) and answer with Groq using doc + web context."""
    web_results = search_web(question)
    answer = answer_question_hybrid(question, document_context, web_results)

    citations = [
        {"url": r["link"], "title": r["title"]}
        for r in web_results
        if r.get("link")
    ]

    return {
        "answer": answer,
        "citations": citations,
        "search_mode": "hybrid",
    }
