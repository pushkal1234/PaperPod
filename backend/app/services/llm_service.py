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

PODCAST_SYSTEM_PROMPT = """You are a world-class podcast script writer. 
Given document content, create an engaging podcast-style conversation between two people:
- **Host** (curious, asks great questions, keeps the conversation flowing)
- **Guest** (the expert, explains concepts clearly with analogies and examples)

Rules:
1. Make it conversational, natural, and engaging — NOT a dry summary.
2. Use casual language, humor, and "aha!" moments.
3. Break complex ideas into simple explanations.
4. Include transitions like "That's fascinating!", "So what you're saying is...", "Let me push back on that..."
5. Cover ALL key points from the document.
6. Output ONLY the dialogue in this exact format (no stage directions, no other text):

Host: [dialogue]
Guest: [dialogue]
Host: [dialogue]
Guest: [dialogue]
...

Start with the Host welcoming listeners and introducing the topic.
End with a natural wrap-up."""

CONTINUE_PROMPT = """Continue the podcast conversation covering these additional points from the document.
Pick up naturally from where you left off — do NOT re-introduce the topic.
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

    # First part: full intro
    script_parts = []
    script = _call_llm([
        {"role": "system", "content": PODCAST_SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a podcast conversation based on this document:\n\n{text_parts[0]}"},
    ])
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
