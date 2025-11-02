"""
Embedding Adapter Protocol.

Defines the interface that all embedding backends must implement.
This allows pluggable embedding models without changing application code.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingAdapter(Protocol):
    """
    Protocol for embedding generation adapters.

    All embedding backends (SentenceTransformers, OpenAI, Cohere, etc.)
    must implement this interface.

    Attributes:
        name: Human-readable model identifier (e.g., "minilm-l6-v2")
        dim: Vector dimensionality (e.g., 384 for MiniLM)
        max_seq_len: Maximum sequence length in tokens (None if unknown)
    """

    @property
    def name(self) -> str:
        """Model name/identifier."""
        ...

    @property
    def dim(self) -> int:
        """Embedding vector dimensionality."""
        ...

    @property
    def max_seq_len(self) -> int | None:
        """Maximum sequence length in tokens, or None if unknown/unlimited."""
        ...

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding vector for text.

        Args:
            text: Input text to embed. Will be truncated if longer than max_seq_len.

        Returns:
            List of floats representing the embedding vector (length = self.dim).

        Raises:
            ValueError: If text is empty or invalid.
        """
        ...
