"""
SentenceTransformer Embedding Adapter.

Implements the EmbeddingAdapter protocol using the sentence-transformers library.
Supports CPU and GPU inference with configurable device selection.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SentenceTransformerAdapter:
    """
    Embedding adapter using SentenceTransformers models.

    This adapter wraps sentence-transformers models and provides a consistent
    interface for embedding generation. It handles device placement (CPU/GPU)
    and exposes model metadata like dimensionality and max sequence length.

    The model is loaded once and cached in memory for fast reuse.
    """

    def __init__(self, model_id: str, device: str = "cpu"):
        """
        Initialize SentenceTransformer adapter.

        Args:
            model_id: HuggingFace model ID (e.g., "sentence-transformers/all-MiniLM-L6-v2")
            device: Device to run model on ("cpu", "cuda", "cuda:0", etc.)

        Raises:
            ImportError: If sentence-transformers is not installed
            ValueError: If model cannot be loaded
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for SentenceTransformerAdapter. "
                "Install with: pip install sentence-transformers"
            ) from e

        logger.info(f"Loading SentenceTransformer model: {model_id}")
        self._model = SentenceTransformer(model_id, device=device)
        self._model_id = model_id
        self._device = device

        # Extract model metadata
        self._dim = self._model.get_sentence_embedding_dimension()

        # Try to get max sequence length from tokenizer
        try:
            if hasattr(self._model, "tokenizer") and hasattr(
                self._model.tokenizer, "model_max_length"
            ):
                self._max_seq_len = self._model.tokenizer.model_max_length
                # Cap at reasonable value (some models report unrealistic values like 1B)
                if self._max_seq_len > 10000:
                    self._max_seq_len = 512  # Conservative fallback
            elif hasattr(self._model, "max_seq_length"):
                self._max_seq_len = self._model.max_seq_length
            else:
                self._max_seq_len = None
        except Exception:
            self._max_seq_len = None

        logger.info(
            f"Model loaded: dim={self._dim}, max_seq_len={self._max_seq_len}, device={device}"
        )

    @property
    def name(self) -> str:
        """Model identifier (HuggingFace ID)."""
        return self._model_id

    @property
    def dim(self) -> int:
        """Embedding dimensionality."""
        return int(self._dim)

    @property
    def max_seq_len(self) -> int | None:
        """Maximum sequence length in tokens."""
        return int(self._max_seq_len) if self._max_seq_len is not None else None

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            ValueError: If text is empty

        Note:
            Text longer than max_seq_len will be automatically truncated
            by the underlying SentenceTransformer model.
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # SentenceTransformers handles truncation automatically
        # Returns numpy array, convert to list
        embedding = self._model.encode(text, convert_to_numpy=True)
        return list(embedding.tolist())  # Ensure it's a list of floats
