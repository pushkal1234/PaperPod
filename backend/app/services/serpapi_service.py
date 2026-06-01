"""Web search service — results combined with document context."""

import logging
import time

import httpx

from app.config import settings
from app.services.llm_service import answer_question_hybrid

logger = logging.getLogger("paperpod")

SERPAPI_URL = "https://serpapi.com/search.json"
MAX_WEB_RESULTS = 5

WEB_RATE_LIMIT_MSG = "You've reached PaperPod's free-tier web search rate limit. Please try again in a few moments."
WEB_SERVICE_ERROR_MSG = "PaperPod's web search service is temporarily busy. Please try again shortly."
WEB_CONFIG_MSG = "Web search is not configured on this server. Please contact support."


def is_configured() -> bool:
    return bool(settings.SERPAPI_API_KEY.strip())


def _is_rate_limit(err_str: str) -> bool:
    low = err_str.lower()
    return any(k in low for k in ["rate_limit", "429", "quota", "too many requests", "limit exceeded"])


def search_web(query: str) -> list[dict]:
    """Run web search with retry. Returns [{title, link, snippet}, ...]."""
    if not is_configured():
        raise RuntimeError(WEB_CONFIG_MSG)

    params = {
        "q": query,
        "api_key": settings.SERPAPI_API_KEY,
        "engine": "google",
        "num": MAX_WEB_RESULTS,
    }

    last_error = None
    _httpx_logger = logging.getLogger("httpx")
    _orig_level = _httpx_logger.level
    for attempt in range(3):
        try:
            # Temporarily suppress httpx logging — it logs full URL including API key
            _httpx_logger.setLevel(logging.WARNING)
            with httpx.Client(timeout=15.0) as client:
                response = client.get(SERPAPI_URL, params=params)
                response.raise_for_status()
                data = response.json()
            _httpx_logger.setLevel(_orig_level)

            if data.get("error"):
                err_msg = data["error"]
                if _is_rate_limit(err_msg):
                    raise RuntimeError(WEB_RATE_LIMIT_MSG)
                raise RuntimeError(WEB_SERVICE_ERROR_MSG)

            def _clean_snippet(s: str) -> str:
                s = (s or "").replace("\r", " ").replace("\n", " ")
                s = " ".join(s.split())
                return s[:400]

            results = []
            for item in data.get("organic_results", [])[:MAX_WEB_RESULTS]:
                link = item.get("link")
                if not link:
                    continue
                snippet = item.get("snippet") or item.get("snippet_highlighted", [""])[0] if isinstance(item.get("snippet_highlighted"), list) else (item.get("snippet") or "")
                results.append({
                    "title": item.get("title") or link,
                    "link": link,
                    "snippet": _clean_snippet(snippet),
                })

            answer_box = data.get("answer_box") or {}
            if answer_box.get("answer") and len(results) < MAX_WEB_RESULTS:
                results.insert(0, {
                    "title": answer_box.get("title") or "Featured answer",
                    "link": answer_box.get("link") or answer_box.get("displayed_link") or "",
                    "snippet": _clean_snippet(answer_box.get("answer") or answer_box.get("snippet", "")),
                })

            logger.info(f"[WebSearch] {len(results)} results for query: {query[:80]}")
            return results

        except RuntimeError as e:
            _httpx_logger.setLevel(_orig_level)
            if _is_rate_limit(str(e)) or WEB_RATE_LIMIT_MSG in str(e):
                raise
            last_error = e
            wait = 5 * (attempt + 1)
            logger.warning(f"[WebSearch] Retry {attempt + 1}/3 after {wait}s: {e}")
            time.sleep(wait)
        except httpx.TimeoutException as e:
            _httpx_logger.setLevel(_orig_level)
            last_error = e
            wait = 10 * (attempt + 1)
            logger.warning(f"[WebSearch] Timeout (attempt {attempt + 1}/3), retrying in {wait}s...")
            time.sleep(wait)
        except Exception as e:
            _httpx_logger.setLevel(_orig_level)
            last_error = e
            err_str = str(e)
            if _is_rate_limit(err_str):
                raise RuntimeError(WEB_RATE_LIMIT_MSG)
            logger.error(f"[WebSearch] Unrecoverable error: {e}")
            raise RuntimeError(WEB_SERVICE_ERROR_MSG)

    raise RuntimeError(WEB_SERVICE_ERROR_MSG)


def answer_with_web_search(question: str, document_context: str) -> dict:
    """Search the web and answer using doc + web context."""
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
