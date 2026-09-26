"""add HNSW ANN index on content_embeddings.embedding (pgvector, cosine)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-24 22:30:00.000000

Adds an approximate-nearest-neighbour (ANN) index to the content embedding
column so movie<->movie similarity and content-based candidate retrieval scale
beyond a sequential scan.

Index design
------------
* Type      : HNSW (Hierarchical Navigable Small World)
* Column    : content_embeddings.embedding  (pgvector ``vector(384)``)
* Dimension : 384  (sentence-transformers/all-MiniLM-L6-v2)
* Operator  : ``vector_cosine_ops``  -> cosine distance (``<=>``)
* Params    : m = 16, ef_construction = 64  (pgvector defaults; good recall/build balance)

Why HNSW (not IVFFlat): HNSW gives high recall without a training/`lists` step
and stays accurate as the catalog grows incrementally (embeddings are inserted
continuously by the Celery backfill), whereas IVFFlat needs periodic retraining
of its cluster lists to keep recall up. Query metric MUST match the index
metric: the application ranks with ``ContentEmbedding.embedding.cosine_distance``
(the ``<=>`` operator), which is exactly what ``vector_cosine_ops`` accelerates.

This migration is a no-op on non-PostgreSQL backends (e.g. the SQLite test DB),
where pgvector/HNSW do not exist.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_content_embeddings_embedding_hnsw"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # HNSW/pgvector are PostgreSQL-only; skip on SQLite and friends.
        return
    # pgvector must be present (created in earlier migration / alembic env).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON content_embeddings "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME};")
