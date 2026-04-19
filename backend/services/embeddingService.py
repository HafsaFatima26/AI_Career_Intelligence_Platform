"""
Embedding Service — Updated for nomic-embed-text
100% free, local, no API key needed.
Output: 768-dim vectors — matches vector(768) in Supabase exactly.
"""
from sentence_transformers import SentenceTransformer
from typing import List

MODEL_NAME = "nomic-ai/nomic-embed-text-v1"
_model: SentenceTransformer = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("📦  Loading nomic-embed-text model (first time ~274MB download)...")
        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
        print("✅  Embedding model loaded.")
    return _model


def embed_text(text: str) -> List[float]:
    """Embed a single string → 768-dim float list."""
    model = get_model()
    embedding = model.encode(
        f"search_document: {text}",
        normalize_embeddings=True
    )
    return embedding.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of strings in one efficient pass."""
    model = get_model()
    prefixed = [f"search_document: {t}" for t in texts]
    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=True
    )
    return embeddings.tolist()


def embed_query(text: str) -> List[float]:
    """Embed a user query — uses query prefix for asymmetric search."""
    model = get_model()
    embedding = model.encode(
        f"search_query: {text}",
        normalize_embeddings=True
    )
    return embedding.tolist()