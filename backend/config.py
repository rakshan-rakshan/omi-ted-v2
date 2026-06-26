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


class _ModelSettings:
    def __init__(self, data: dict[str, Any]) -> None:
        self.primary_provider: str = data.get("primary_provider", "ollama")
        self.ollama_base_url: str = data.get("ollama_base_url", "http://localhost:11434")
        self.embedding_model: str = data.get("embedding_model", "bge-m3")
        self.embedding_dim: int = data.get("embedding_dim", 768)
        self.query_rewrite_model: str = data.get("query_rewrite_model", "qwen2.5:3b")
        self.synthesis_model: str = data.get("synthesis_model", "qwen2.5:7b-instruct")
        self.reranker_model: str = data.get("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.reranker_max_length: int = data.get("reranker_max_length", 512)
        # LLM-agnostic routing for RAG generation. provider: ollama (local/free/slow)
        # | openrouter (paid/fast). openrouter_model is the slug used when a step
        # routes to OpenRouter (synthesis or query rewrite).
        self.synthesis_provider: str = data.get("synthesis_provider", "ollama")
        self.rewrite_provider: str = data.get("rewrite_provider", "ollama")
        self.openrouter_model: str = data.get("openrouter_model", "anthropic/claude-haiku-4.5")


class _RAGPipelineSettings:
    def __init__(self, data: dict[str, Any]) -> None:
        self.enable_query_rewrite: bool = data.get("enable_query_rewrite", True)
        self.enable_reranking: bool = data.get("enable_reranking", True)
        self.enable_context_budget: bool = data.get("enable_context_budget", True)
        self.max_context_tokens: int = data.get("max_context_tokens", 3000)
        self.max_rewritten_terms: int = data.get("max_rewritten_terms", 5)


class _Settings:
    def __init__(self) -> None:
        p = Path(__file__).parent / "config.yaml"
        with open(p) as f:
            raw: dict = yaml.safe_load(f) or {}
        self.rag = _RagSettings(raw.get("rag", {}))
        self.models = _ModelSettings(raw.get("models", {}))
        self.rag_pipeline = _RAGPipelineSettings(raw.get("rag_pipeline", {}))
        self._raw = raw


settings = _Settings()
