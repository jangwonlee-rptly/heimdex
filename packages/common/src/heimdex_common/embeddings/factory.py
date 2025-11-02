"""
Embedding Adapter Factory.

Provides singleton access to embedding adapters with configuration validation.
Supports model registry for friendly short names mapped to HuggingFace IDs.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from heimdex_common.embeddings.adapter import EmbeddingAdapter

logger = logging.getLogger(__name__)

# Model Registry: Short name → Model configuration
# This allows using friendly names like "minilm-l6-v2" instead of full HF IDs
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "minilm-l6-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "max_seq_len": 256,
        "description": "Fast, small model. Good for most use cases.",
    },
    "mpnet-base": {
        "hf_id": "sentence-transformers/all-mpnet-base-v2",
        "dim": 768,
        "max_seq_len": 384,
        "description": "Higher quality, slower. Best performance.",
    },
    "minilm-l12-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L12-v2",
        "dim": 384,
        "max_seq_len": 256,
        "description": "Balanced quality/speed. Slightly better than L6.",
    },
}


def resolve_model_id(model_name: str) -> tuple[str, int | None]:
    """
    Resolve model name to HuggingFace ID and expected dimensionality.

    Args:
        model_name: Short name (e.g., "minilm-l6-v2") or full HF ID

    Returns:
        Tuple of (hf_id, expected_dim)
        expected_dim is None if model is unknown (will be inferred after load)

    Example:
        >>> resolve_model_id("minilm-l6-v2")
        ("sentence-transformers/all-MiniLM-L6-v2", 384)

        >>> resolve_model_id("sentence-transformers/custom-model")
        ("sentence-transformers/custom-model", None)
    """
    if model_name in MODEL_REGISTRY:
        config = MODEL_REGISTRY[model_name]
        return str(config["hf_id"]), int(config["dim"])

    # Unknown model: assume it's a full HF ID
    logger.warning(
        f"Model '{model_name}' not in registry. "
        f"Treating as HuggingFace ID. "
        f"Available models: {list(MODEL_REGISTRY.keys())}"
    )
    return model_name, None


@lru_cache(maxsize=1)
def get_adapter() -> EmbeddingAdapter:
    """
    Get the configured embedding adapter (singleton).

    This function is cached, so the model is loaded only once per process.

    Configuration (via environment variables):
        EMBEDDING_BACKEND: Backend type (default: "sentence")
        EMBEDDING_MODEL_NAME: Model name or HF ID (default: "minilm-l6-v2")
        EMBEDDING_DEVICE: Device for inference (default: "cpu", can be "cuda")

    Returns:
        Configured EmbeddingAdapter instance

    Raises:
        ValueError: If backend is unsupported or model cannot be loaded

    Example:
        >>> adapter = get_adapter()
        >>> adapter.name
        'sentence-transformers/all-MiniLM-L6-v2'
        >>> adapter.dim
        384
    """
    backend = os.getenv("EMBEDDING_BACKEND", "sentence")
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "minilm-l6-v2")
    device = os.getenv("EMBEDDING_DEVICE", "cpu")

    if backend == "sentence":
        from heimdex_common.embeddings.adapters.sentence import SentenceTransformerAdapter

        hf_id, expected_dim = resolve_model_id(model_name)

        logger.info(
            f"Initializing SentenceTransformer adapter: "
            f"model={model_name} (HF: {hf_id}), device={device}"
        )

        adapter = SentenceTransformerAdapter(hf_id, device=device)

        # Validate dimension matches registry (if known)
        if expected_dim and adapter.dim != expected_dim:
            logger.warning(
                f"⚠️  Model dimension mismatch!\n"
                f"   Registry expected: {expected_dim}-dim\n"
                f"   Model reports:     {adapter.dim}-dim\n"
                f"   Using actual model dimension: {adapter.dim}"
            )

        return adapter

    else:
        raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}. Supported: sentence")


def validate_adapter_dimension(vector_size: int) -> None:
    """
    Validate that adapter dimension matches configured VECTOR_SIZE.

    This should be called at startup to fail fast if configuration is invalid.

    Args:
        vector_size: Expected vector size from VECTOR_SIZE config

    Raises:
        ValueError: If dimensions don't match

    Example:
        >>> from heimdex_common.config import get_config
        >>> config = get_config()
        >>> validate_adapter_dimension(config.vector_size)
    """
    validate_on_startup = os.getenv("EMBEDDING_VALIDATE_ON_STARTUP", "true").lower() == "true"

    if not validate_on_startup:
        logger.warning("⚠️  EMBEDDING_VALIDATE_ON_STARTUP=false - skipping dimension check")
        return

    adapter = get_adapter()

    if adapter.dim != vector_size:
        raise ValueError(
            f"❌ Embedding dimension mismatch!\n"
            f"\n"
            f"   Model '{adapter.name}' produces {adapter.dim}-dim vectors\n"
            f"   but VECTOR_SIZE={vector_size}\n"
            f"\n"
            f"   → Fix: Set VECTOR_SIZE={adapter.dim} in your .env file\n"
            f"\n"
            f"   To bypass this check (not recommended):\n"
            f"   Set EMBEDDING_VALIDATE_ON_STARTUP=false\n"
        )

    logger.info(
        f"✓ Dimension validation passed: "
        f"model={adapter.name}, dim={adapter.dim}, VECTOR_SIZE={vector_size}"
    )
