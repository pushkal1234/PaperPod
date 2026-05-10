from groq import Groq

from app.config import settings

_client = Groq(api_key=settings.GROQ_API_KEY)

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

QA_SYSTEM_PROMPT = """You are a helpful assistant that answers questions about a document.
You will be given relevant context from the document and a user question.

Rules:
1. Answer based on the provided context FIRST.
2. If the context doesn't contain enough information, say so and provide your best general knowledge answer.
3. Be concise but thorough.
4. Speak naturally as if explaining to a friend."""


def generate_podcast_script(document_text: str) -> str:
    """Generate a podcast-style dialogue from document text using Groq LLM."""
    truncated = document_text[:12000]

    response = _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": PODCAST_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Create a podcast conversation based on this document:\n\n{truncated}",
            },
        ],
        temperature=0.8,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def answer_question(question: str, context_chunks: list[str]) -> str:
    """Answer a question using document context via Groq LLM."""
    context = "\n\n---\n\n".join(context_chunks)

    response = _client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context from the document:\n\n{context}\n\n---\n\nQuestion: {question}",
            },
        ],
        temperature=0.5,
        max_tokens=1024,
    )
    return response.choices[0].message.content
