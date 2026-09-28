import threading
from typing import Sequence

from huggingface_hub import InferenceClient

from app.core.config import settings


class SentenceEncoder:
    """
    Thread-safe singleton wrapper for text embedding inference.

    Embeddings are generated remotely via the HuggingFace Inference API
    (feature-extraction) instead of a local model. This keeps the runtime
    image small (no torch / sentence-transformers) while producing vectors
    from the same model, so previously stored embeddings remain compatible.
    """

    _instance: "SentenceEncoder | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.model_name = settings.EMBEDDING_MODEL
        self.expected_dimension = settings.VECTOR_DIMENSION
        # Informational endpoint assembled from the configured router base.
        self.api_url = f"{settings.HF_API_URL.rstrip('/')}/{self.model_name}"
        self._client: InferenceClient | None = None

    @classmethod
    def get_instance(cls) -> "SentenceEncoder":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_client(self) -> InferenceClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = InferenceClient(
                        model=self.model_name,
                        provider="hf-inference",
                        token=settings.HF_API_TOKEN,
                        timeout=60.0,
                    )
        return self._client

    def _request(self, inputs: str | list[str]) -> list:
        """
        Calls Hugging Face's current feature-extraction provider API.
        """
        client = self._get_client()
        data = client.feature_extraction(inputs)
        return data.tolist() if hasattr(data, "tolist") else data

    def _validate(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self.expected_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.expected_dimension}, got {len(vector)}"
            )
        return [float(x) for x in vector]

    def encode(self, text: str) -> list[float]:
        """Generates a dense vector embedding for a single text."""
        if not text or not text.strip():
            text = "empty"
        data = self._request(text)
        # feature-extraction may return [dim] or [1, dim]
        vector = data[0] if data and isinstance(data[0], list) else data
        return self._validate(vector)

    def encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generates dense vector embeddings for a batch of texts."""
        if not texts:
            return []
        cleaned_texts = [t if (t and t.strip()) else "empty" for t in texts]
        data = self._request(list(cleaned_texts))
        return [self._validate(vec) for vec in data]
