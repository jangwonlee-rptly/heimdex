"""
Embedding generation infrastructure for Heimdex.

This package provides a pluggable adapter pattern for generating text embeddings
using various backends (SentenceTransformers, OpenAI, Cohere, etc.).

The adapter abstraction allows swapping embedding models without changing
application code, enabling experimentation and model upgrades.
"""

from heimdex_common.embeddings.adapter import EmbeddingAdapter
from heimdex_common.embeddings.factory import get_adapter

__all__ = [
    "EmbeddingAdapter",
    "get_adapter",
]
