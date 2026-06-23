"""
Multilingual embedding service. Uses sentence-transformers with e5 models.
Singleton model loader for efficiency.

Gracefully degrades if sentence-transformers or model is unavailable.
"""
from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDER = None
_EMBED_DIM = 768
_MODEL_NAME = os.getenv("EMBEDDER_MODEL", "intfloat/multilingual-e5-base")
_AVAILABLE = True


def is_available() -> bool:
    """Check if the embedding model is cached locally.

    Does NOT import sentence-transformers (which can hang on download).
    Only checks if model files exist on disk via huggingface_hub cache.
    """
    global _AVAILABLE
    if not _AVAILABLE:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(_MODEL_NAME, "model.safetensors")
        if path is None:
            path = try_to_load_from_cache(_MODEL_NAME, "pytorch_model.bin")
        if path is not None:
            return True
        logger.warning(
            "Embedding model %s not cached locally — "
            "run: python -c \"from sentence_transformers import SentenceTransformer; "
            "SentenceTransformer('%s')\" to download",
            _MODEL_NAME, _MODEL_NAME,
        )
    except Exception:
        pass
    _AVAILABLE = False
    return False


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        if not is_available():
            raise RuntimeError("Embeddings unavailable: sentence-transformers not installed")
        from sentence_transformers import SentenceTransformer
        try:
            logger.info("Loading embedder: %s", _MODEL_NAME)
            _EMBEDDER = SentenceTransformer(_MODEL_NAME, device="cpu")
            _EMBEDDER.eval()
        except Exception as exc:
            logger.error("Failed to load embedder %s: %s", _MODEL_NAME, exc)
            raise RuntimeError(f"Embedding model {_MODEL_NAME} could not be loaded") from exc
    return _EMBEDDER


async def embed_query(text: str) -> list[float] | None:
    """Embed a query string. Returns None if embeddings unavailable."""
    if not is_available():
        return None
    try:
        model = _get_embedder()
        emb = model.encode(["query: " + text], normalize_embeddings=True, show_progress_bar=False)
        return emb[0].tolist()
    except Exception as exc:
        logger.warning("embed_query failed: %s", exc)
        return None


async def embed_chunks(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Embed chunk texts. Returns empty list if embeddings unavailable."""
    if not texts or not is_available():
        return []
    try:
        model = _get_embedder()
        prefixed = ["passage: " + t for t in texts]
        all_embs = []
        for i in range(0, len(prefixed), batch_size):
            batch = prefixed[i:i + batch_size]
            embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
            all_embs.extend(embs.tolist())
        return all_embs
    except Exception as exc:
        logger.warning("embed_chunks failed: %s", exc)
        return []


async def embed_chunk(text: str) -> list[float] | None:
    embs = await embed_chunks([text])
    return embs[0] if embs else None


def embed_dim() -> int:
    return _EMBED_DIM
