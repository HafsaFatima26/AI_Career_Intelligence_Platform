"""
Calls Google Gemini text-embedding-004 to generate 768-dim embeddings.
Offloads all ML compute to Google's API – zero local model memory.
"""
import os
import google.generativeai as genai
from typing import List

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
EMBED_MODEL = "models/text-embedding-004"


def embed_text(text: str) -> List[float]:
    """Returns a 768-dimensional embedding vector."""
    result = genai.embed_content(
        model=EMBED_MODEL,
        content=text,
        task_type="RETRIEVAL_DOCUMENT",
    )
    return result["embedding"]


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embeds a list of strings – handles Gemini's per-request limits."""
    embeddings = []
    for chunk in _chunk(texts, 100):
        for t in chunk:
            embeddings.append(embed_text(t))
    return embeddings


def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
