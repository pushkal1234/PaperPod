"""Unit tests for the token / rate-limit optimizations:

  (A) prompt-cache-friendly podcast prompt  -> _build_podcast_prompt
  (B) lossless document compaction           -> compact_document_text
  (C) Groq TPM-cooldown router               -> _groq_in_cooldown / _trip_groq_cooldown

Dependency-free (stdlib ``unittest``). Run from the ``backend`` directory:

    ./venv/bin/python -m unittest discover -s tests

The suite is also collected by pytest if it is ever added to the project.
"""

import time
import unittest

from app.services.document_service import (
    _COMPACTION_MIN_CHARS,
    compact_document_text,
)
from app.services import llm_service


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pad(text: str, min_chars: int = _COMPACTION_MIN_CHARS + 500) -> str:
    """Grow ``text`` past the compaction skip threshold with neutral prose so the
    real assertions exercise the compaction logic rather than the short-doc
    early-return."""
    filler_line = (
        "This is a genuine sentence of document prose that carries real meaning "
        "and must always survive compaction untouched.\n"
    )
    while len(text) < min_chars:
        text += filler_line
    return text


# --------------------------------------------------------------------------- #
# (B) compact_document_text
# --------------------------------------------------------------------------- #
class TestCompactDocumentText(unittest.TestCase):
    def test_short_doc_returned_unchanged(self):
        """Docs below the threshold must be returned byte-for-byte."""
        doc = "Short document with a 12 page number line.\n12\nAnd more text."
        self.assertLess(len(doc), _COMPACTION_MIN_CHARS)
        self.assertEqual(compact_document_text(doc), doc)

    def test_empty_and_none(self):
        self.assertEqual(compact_document_text(""), "")
        self.assertIsNone(compact_document_text(None))

    def test_repeated_header_deduped_first_kept(self):
        body = "\n".join(
            f"ACME Confidential\nReal analysis paragraph number {i} with meaningful "
            f"content that must be preserved verbatim across the document body."
            for i in range(8)
        )
        out = compact_document_text(_pad(body))
        # The running header collapses to a single occurrence...
        self.assertEqual(out.count("ACME Confidential"), 1)
        # ...while every content paragraph survives.
        for i in range(8):
            self.assertIn(f"paragraph number {i}", out)

    def test_page_number_variants_removed(self):
        variants = ["12", "- 12 -", "Page 3", "Page 3 of 40", "12 / 40", "  7  "]
        body = ""
        for i, v in enumerate(variants):
            body += f"Section {i}: substantive prose that should be kept in full.\n{v}\n"
        out = compact_document_text(_pad(body))
        for i in range(len(variants)):
            self.assertIn(f"Section {i}:", out)
        # No standalone folio line should remain.
        for line in out.split("\n"):
            self.assertFalse(
                line.strip() in {"12", "- 12 -", "Page 3", "Page 3 of 40", "12 / 40", "7"},
                f"page-number line survived: {line!r}",
            )

    def test_hyphenation_rejoined(self):
        body = "The archi-\ntecture of the sys-\ntem is well documented here.\n"
        body += "A soft\u00adhyphen exam\u00ad\nple also joins cleanly.\n"
        out = compact_document_text(_pad(body))
        self.assertIn("architecture of the system", out)
        self.assertIn("example also joins", out)

    def test_blank_line_runs_collapsed(self):
        body = "First paragraph of real content.\n\n\n\n\nSecond paragraph of real content.\n"
        out = compact_document_text(_pad(body))
        self.assertNotIn("\n\n\n", out)
        self.assertIn("First paragraph", out)
        self.assertIn("Second paragraph", out)

    def test_never_returns_larger_output(self):
        body = _pad("Ordinary prose without any noise to strip at all. ")
        out = compact_document_text(body)
        self.assertLessEqual(len(out), len(body))

    def test_all_numeric_doc_triggers_safety_gate(self):
        """A doc that is mostly standalone numbers would lose >40% to the
        page-number rule, so the safety gate must return the ORIGINAL."""
        body = "\n".join(str(n) for n in range(700))  # hundreds of lone-number lines, > threshold
        self.assertGreaterEqual(len(body), _COMPACTION_MIN_CHARS)
        out = compact_document_text(body)
        self.assertEqual(out, body)

    def test_table_rows_preserved(self):
        """Pipe/space-delimited table rows carry numbers inline (not as lone
        lines) and must survive intact; only lone folios are removed."""
        table = (
            "Quarterly Revenue Table\n"
            "Region | Q1 | Q2 | Q3 | Q4\n"
            "North  | 120 | 135 | 150 | 175\n"
            "South  | 90  | 95  | 110 | 130\n"
            "EMEA   | 200 | 210 | 225 | 240\n"
        )
        out = compact_document_text(_pad(table))
        self.assertIn("Region | Q1 | Q2 | Q3 | Q4", out)
        self.assertIn("North  | 120 | 135 | 150 | 175", out)
        self.assertIn("EMEA   | 200 | 210 | 225 | 240", out)

    def test_code_block_preserved(self):
        """Indentation and symbols in code must be preserved (we never collapse
        intra-line whitespace)."""
        code = (
            "Here is the reference implementation:\n"
            "def fib(n):\n"
            "    if n < 2:\n"
            "        return n\n"
            "    return fib(n - 1) + fib(n - 2)\n"
            "\n"
            "result = fib(10)  # 55\n"
        )
        out = compact_document_text(_pad(code))
        self.assertIn("    if n < 2:", out)
        self.assertIn("        return n", out)
        self.assertIn("    return fib(n - 1) + fib(n - 2)", out)
        self.assertIn("result = fib(10)  # 55", out)

    def test_prose_is_never_reworded(self):
        sentence = "The mitochondrion is the powerhouse of the cell, per the source."
        body = _pad("\n".join(f"{sentence} ({i})" for i in range(20)))
        out = compact_document_text(body)
        # Exact wording is retained for every line.
        for i in range(20):
            self.assertIn(f"{sentence} ({i})", out)


# --------------------------------------------------------------------------- #
# (A) prompt-cache-friendly prompt
# --------------------------------------------------------------------------- #
class TestPromptCacheOptimize(unittest.TestCase):
    def setUp(self):
        self._orig = llm_service.settings.PROMPT_CACHE_OPTIMIZE

    def tearDown(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = self._orig

    def test_prefix_identical_across_document_sizes(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = True
        p1 = llm_service._build_podcast_prompt(100, 120, procedural=False)
        p2 = llm_service._build_podcast_prompt(140, 160, procedural=False)
        pre1 = p1.split("TARGET LENGTH")[0]
        pre2 = p2.split("TARGET LENGTH")[0]
        # Everything before the trailing spec is a byte-stable, cacheable prefix.
        self.assertEqual(pre1, pre2)
        self.assertGreater(len(pre1), 0.4 * len(p1))

    def test_trailing_spec_has_correct_numbers(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = True
        p = llm_service._build_podcast_prompt(100, 120, procedural=False)
        self.assertIn("TARGET LENGTH: at least 100 and up to 120", p)

    def test_all_critical_rules_still_present(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = True
        p = llm_service._build_podcast_prompt(100, 120, procedural=False)
        for marker in ("0.", "1.", "8.", "9.", "10.", "11.", "Host:", "Guest:"):
            self.assertIn(marker, p)

    def test_disabled_restores_inline_numbers(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = False
        p = llm_service._build_podcast_prompt(100, 120, procedural=False)
        self.assertNotIn("TARGET LENGTH", p)
        self.assertIn("AT LEAST 100 and up", p)

    def test_short_and_procedural_variants_render(self):
        llm_service.settings.PROMPT_CACHE_OPTIMIZE = True
        short = llm_service._build_podcast_prompt(12, 14, procedural=False)
        proc = llm_service._build_podcast_prompt(60, 80, procedural=True)
        self.assertIn("TARGET LENGTH", short)
        self.assertIn("TARGET LENGTH", proc)


# --------------------------------------------------------------------------- #
# (C) Groq TPM-cooldown router
# --------------------------------------------------------------------------- #
class TestGroqCooldown(unittest.TestCase):
    def setUp(self):
        self._orig_secs = llm_service.settings.GROQ_TPM_COOLDOWN_SECONDS
        llm_service._groq_cooldown_until = 0.0  # reset shared state

    def tearDown(self):
        llm_service.settings.GROQ_TPM_COOLDOWN_SECONDS = self._orig_secs
        llm_service._groq_cooldown_until = 0.0

    def test_starts_not_in_cooldown(self):
        self.assertFalse(llm_service._groq_in_cooldown())

    def test_trip_enters_cooldown(self):
        llm_service.settings.GROQ_TPM_COOLDOWN_SECONDS = 60
        llm_service._trip_groq_cooldown("(test)")
        self.assertTrue(llm_service._groq_in_cooldown())

    def test_disabled_is_noop(self):
        llm_service.settings.GROQ_TPM_COOLDOWN_SECONDS = 0
        llm_service._trip_groq_cooldown("(disabled)")
        self.assertFalse(llm_service._groq_in_cooldown())

    def test_cooldown_expires(self):
        llm_service.settings.GROQ_TPM_COOLDOWN_SECONDS = 0.05
        llm_service._trip_groq_cooldown("(short)")
        self.assertTrue(llm_service._groq_in_cooldown())
        time.sleep(0.1)
        self.assertFalse(llm_service._groq_in_cooldown())


if __name__ == "__main__":
    unittest.main(verbosity=2)
