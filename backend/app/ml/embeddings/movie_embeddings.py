# Deprecated: local SentenceTransformer embeddings have been removed.
# Embeddings are now generated via the HuggingFace Inference API.
# See app/ml/embeddings/sentence_encoder.py (SentenceEncoder) and
# app/ml/embeddings/service.py (MovieEmbeddingService).
#
# This module is intentionally left empty to avoid importing torch /
# sentence-transformers into the runtime image. It is not imported anywhere.
