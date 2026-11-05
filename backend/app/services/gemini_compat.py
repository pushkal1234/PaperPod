"""Turn Gemini "thinking" off in whatever form each model accepts.

We always want thinking off: reasoning tokens eat the output budget and slow
every call. Models disagree on how to say that:

- 2.5 Flash, 3.x Flash and 3.1 Flash-Lite accept ``thinking_budget=0``.
- 3.5 Flash-Lite rejects ``thinking_budget`` with a bare
  ``400 INVALID_ARGUMENT`` and wants ``thinking_level="minimal"`` instead.
- Some models (e.g. Gemma) accept neither, so we send no thinking config.

From Dec 1, 2026 Google also routes ``gemini-2.5-flash`` to 3.5 Flash-Lite, so
the primary model will change behaviour under us. So when a model rejects one
form we try the next, and remember what worked per model.
"""

import logging
import threading

from google.genai import types

logger = logging.getLogger("paperpod")

_BUDGET0, _MINIMAL, _NONE = "budget0", "minimal", "none"
_ORDER = (_BUDGET0, _MINIMAL, _NONE)

# Known up front, so the first call doesn't spend a doomed round-trip.
_mode_by_model: dict[str, str] = {
    "gemini-3.5-flash-lite": _MINIMAL,
    "gemini-flash-lite-latest": _MINIMAL,
}
_lock = threading.Lock()


def _thinking_config(mode: str):
    if mode == _BUDGET0:
        return types.ThinkingConfig(thinking_budget=0)
    if mode == _MINIMAL:
        return types.ThinkingConfig(thinking_level="minimal")
    return None


def _rejects_thinking_config(err: Exception) -> bool:
    """A 400 about the request shape, not quota, overload or a bad model id."""
    low = str(err).lower()
    if "400" not in low and "invalid_argument" not in low:
        return False
    return "thinking" in low or "invalid argument" in low


def generate_without_thinking(client, model: str, contents, **config_kwargs):
    """``client.models.generate_content`` with thinking off for ``model``.

    ``config_kwargs`` go to ``GenerateContentConfig`` (temperature,
    max_output_tokens, system_instruction, ...). Raises like the SDK does.
    """
    with _lock:
        start = _mode_by_model.get(model, _BUDGET0)
    modes = _ORDER[_ORDER.index(start):]
    for i, mode in enumerate(modes):
        cfg = types.GenerateContentConfig(thinking_config=_thinking_config(mode), **config_kwargs)
        try:
            response = client.models.generate_content(model=model, contents=contents, config=cfg)
        except Exception as e:  # noqa: BLE001 — only a rejected thinking form moves on
            if i + 1 < len(modes) and _rejects_thinking_config(e):
                logger.info(
                    f"[LLM] {model} rejected thinking form {mode!r}; retrying with {modes[i + 1]!r}"
                )
                continue
            raise
        if mode != start:
            with _lock:
                _mode_by_model[model] = mode
            logger.info(f"[LLM] {model}: thinking off via {mode!r} from now on")
        return response
