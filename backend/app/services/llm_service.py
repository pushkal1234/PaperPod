import logging
import time

from groq import Groq

from app.config import settings

logger = logging.getLogger("paperpod")

_client = Groq(api_key=settings.GROQ_API_KEY)

# Groq free tier limit: 6000 TPM for llama-3.1-8b-instant
# ~4 chars ≈ 1 token, so we keep input text under ~3500 tokens (~14000 chars)
# leaving room for system prompt + output tokens
MAX_INPUT_CHARS = 6000

def _build_podcast_prompt(doc_length: int) -> str:
    """Build system prompt with length guidance scaled to document size."""
    # Scale: ~1 min of audio ≈ 150 words of dialogue ≈ 6-8 exchanges
    if doc_length < 2000:       # ~1 page
        target = "8-10 exchanges (about 2 minutes of audio)"
    elif doc_length < 5000:     # 2-4 pages
        target = "12-16 exchanges (about 3-4 minutes of audio)"
    elif doc_length < 10000:    # 5-8 pages
        target = "16-20 exchanges (about 4-5 minutes of audio)"
    else:                       # 9+ pages
        target = "20-25 exchanges (about 5-6 minutes of audio)"

    return f"""You are a world-class podcast script writer. 
Given document content, create an engaging podcast-style conversation between two people:
- **Host** (curious, asks great questions, keeps the conversation flowing)
- **Guest** (the expert, explains concepts clearly with analogies and examples)

Rules:
1. Make it conversational, natural, and engaging — NOT a dry summary.
2. Use casual language, humor, and "aha!" moments.
3. Break complex ideas into simple explanations.
4. Include transitions like "That's fascinating!", "So what you're saying is...", "Let me push back on that..."
5. Focus on the TOP 3-5 most important insights — do NOT try to cover every single detail.
6. Keep it CONCISE and punchy. Target: {target}.
7. Each speaker turn should be 1-3 sentences MAX. No long monologues.
8. Output ONLY the dialogue in this exact format (no stage directions, no other text):

Host: [dialogue]
Guest: [dialogue]
Host: [dialogue]
Guest: [dialogue]
...

Start with the Host giving a brief, energetic intro to the topic (1 sentence).
End with a quick natural wrap-up (1-2 exchanges)."""


CONTINUE_PROMPT = """Continue the podcast conversation covering these additional points from the document.
Pick up naturally from where you left off — do NOT re-introduce the topic.
Keep it concise — focus on the most important new insights only (8-10 more exchanges max).
Output ONLY dialogue in Host:/Guest: format."""

QA_SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a document.
You will be given relevant context from the document and a user question.

Rules:
1. Answer based on the provided context FIRST.
2. If the context doesn't contain enough information, say so and provide your best general knowledge answer.
3. Be concise but thorough.
4. Speak naturally as if explaining to a friend."""


def _call_llm(messages: list[dict], temperature: float = 0.8, max_tokens: int = 2048) -> str:
    """Call Groq LLM with retry on rate limit."""
    for attempt in range(3):
        try:
            response = _client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "rate_limit" in str(e).lower() or "413" in str(e):
                wait = 30 * (attempt + 1)
                logger.warning(f"Rate limited, waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("LLM call failed after 3 retries")


def generate_podcast_script(document_text: str) -> str:
    """Generate a podcast-style dialogue from document text using Groq LLM.
    
    For large documents, splits into chunks and generates script in parts
    with waits between calls to respect Groq free-tier rate limits.
    """
    text_parts = []
    for i in range(0, len(document_text), MAX_INPUT_CHARS):
        text_parts.append(document_text[i:i + MAX_INPUT_CHARS])

    logger.info(f"Document split into {len(text_parts)} part(s) for LLM")

    # First part: full intro with length-scaled prompt
    system_prompt = _build_podcast_prompt(len(document_text))
    # Scale max output tokens: small docs get shorter scripts
    max_out = 1024 if len(document_text) < 3000 else 1536 if len(document_text) < 8000 else 2048
    script_parts = []
    script = _call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Create a podcast conversation based on this document:\n\n{text_parts[0]}"},
    ], max_tokens=max_out)
    script_parts.append(script)

    # Additional parts: continue the conversation
    for idx, part in enumerate(text_parts[1:], start=2):
        logger.info(f"Waiting 60s for rate limit before part {idx}/{len(text_parts)}...")
        time.sleep(60)
        continuation = _call_llm([
            {"role": "system", "content": CONTINUE_PROMPT},
            {"role": "user", "content": f"Additional document content:\n\n{part}"},
        ])
        script_parts.append(continuation)

    return "\n\n".join(script_parts)


def answer_question(question: str, context_chunks: list[str]) -> str:
    """Answer a question using document context via Groq LLM."""
    context = "\n\n---\n\n".join(context_chunks)
    # Keep context within limits
    context = context[:MAX_INPUT_CHARS]

    return _call_llm(
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context from the document:\n\n{context}\n\n---\n\nQuestion: {question}"},
        ],
        temperature=0.5,
        max_tokens=1024,
    )
