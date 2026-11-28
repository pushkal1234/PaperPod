"""Plan-aware wording for user-facing failure messages.

Applied at READ time (when a failed document or Q&A error is returned), so
documents that already failed show the corrected text without regenerating.
"""

PAID_AUDIO_BUSY_MSG = (
    "We're seeing peak traffic right now as members rush to secure Founding Member "
    "seats, and our audio service couldn't finish your podcast. Please try again in "
    "a little while, or split your document into shorter parts — those finish faster."
)
PAID_OCR_BUSY_MSG = (
    "We're seeing peak traffic right now and our text-recognition service couldn't "
    "finish reading your document. Please try again in a little while."
)
PAID_WEB_BUSY_MSG = (
    "We're seeing peak traffic right now and web search couldn't finish. Please try "
    "again in a little while."
)
PAID_BUSY_MSG = (
    "We're seeing peak traffic right now and couldn't finish this request. Please try "
    "again in a little while."
)

# "Too long" messages name the free plan, but Premium has the SAME length ceiling
# (see entitlements.get_entitlements), so for paid users drop the plan reference.
_PAID_REWRITES = [
    (
        "which is beyond what PaperPod's free plan supports. The free tier covers documents",
        "which is beyond what PaperPod currently supports. PaperPod covers documents",
    ),
    (
        "aren't supported on PaperPod's free plan, which covers",
        "aren't supported yet. PaperPod covers",
    ),
    (
        "are limited on PaperPod's free plan (up to",
        "are limited on PaperPod (up to",
    ),
]


def user_facing_error(msg: str | None, is_paid: bool) -> str | None:
    """Return ``msg`` worded for the owner's plan (unchanged for free users)."""
    if not msg or not is_paid:
        return msg
    low = msg.lower()
    if "free-tier" in low:
        if "synthesizing audio" in low:
            return PAID_AUDIO_BUSY_MSG
        if "ocr" in low:
            return PAID_OCR_BUSY_MSG
        if "web search" in low:
            return PAID_WEB_BUSY_MSG
        return PAID_BUSY_MSG
    for old, new in _PAID_REWRITES:
        msg = msg.replace(old, new)
    return msg
