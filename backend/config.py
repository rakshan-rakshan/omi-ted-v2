"""
Typed settings from config.yaml.
Usage: from config import settings
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _RagSettings:
    def __init__(self, data: dict[str, Any]) -> None:
        self.embedder: str = data.get("embedder", "intfloat/multilingual-e5-base")
        self.embed_dim: int = data.get("embed_dim", 768)
        self.rrf_k: int = data.get("rrf_k", 60)
        self.top_k_search: int = data.get("top_k_search", 20)
        self.top_k_ask: int = data.get("top_k_ask", 5)
        self.chunk_min_words: int = data.get("chunk_min_words", 80)
        self.chunk_target_words: int = data.get("chunk_target_words", 250)
        self.chunk_max_words: int = data.get("chunk_max_words", 500)
        self.chunk_similarity_threshold: float = data.get("chunk_similarity_threshold", 0.85)
        self.generation_model: str = data.get("generation_model", "openrouter/anthropic/claude-3-haiku")
        self.generation_max_tokens: int = data.get("generation_max_tokens", 1024)
        self.hnsw_m: int = data.get("hnsw_m", 16)
        self.hnsw_ef_construction: int = data.get("hnsw_ef_construction", 200)
        self.hnsw_ef_search: int = data.get("hnsw_ef_search", 40)


class _Settings:
    def __init__(self) -> None:
        p = Path(__file__).parent / "config.yaml"
        with open(p) as f:
            raw: dict = yaml.safe_load(f) or {}
        self.rag = _RagSettings(raw.get("rag", {}))
        self._raw = raw


settings = _Settings()
