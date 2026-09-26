import threading
from typing import Sequence

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
        # Endpoint like: https://api-inference.huggingface.co/pipeline/feature-extraction/{model}
        self.api_url = f"{settings.HF_API_URL.rstrip('/')}/{self.model_name}"
        self._client: httpx.Client | None = None

    @classmethod
    def get_instance(cls) -> "SentenceEncoder":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    headers = {"Content-Type": "application/json"}
                    if settings.HF_API_TOKEN:
                        headers["Authorization"] = f"Bearer {settings.HF_API_TOKEN}"
                    self._client = httpx.Client(
                        headers=headers,
                        timeout=httpx.Timeout(60.0, connect=10.0),
                    )
        return self._client

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((httpx.HTTPError,)),
        reraise=True,
    )
    def _request(self, inputs: str | list[str]) -> list:
        """
        Calls the HF feature-extraction endpoint. Retries on transient errors
        and on 503 (model still loading on HF's side).
        """
        client = self._get_client()
        payload = {"inputs": inputs, "options": {"wait_for_model": True}}
        resp = client.post(self.api_url, json=payload)
        # 503 = model loading; raise so tenacity retries with backoff
        if resp.status_code == 503:
            raise httpx.HTTPError("HF model is loading (503)")
        resp.raise_for_status()
        return resp.json()

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
