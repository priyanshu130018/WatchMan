"""create unified content schema and migrate movie records

Revision ID: 3d8b1c4e5f6a
Revises: 27fe0b4e26ff
Create Date: 2026-09-20 17:30:00.000000

"""
from typing import Sequence, Union

import pgvector.sqlalchemy
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3d8b1c4e5f6a"
down_revision: Union[str, Sequence[str], None] = "27fe0b4e26ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # 1. Unified Contents Table
    op.create_table(
        "contents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False, server_default="movie"),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("original_title", sa.String(length=500), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("release_date", sa.String(length=50), nullable=True),
        sa.Column("poster_path", sa.String(length=500), nullable=True),
        sa.Column("backdrop_path", sa.String(length=500), nullable=True),
        sa.Column("original_language", sa.String(length=20), nullable=True),
        sa.Column("popularity", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("vote_average", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("adult", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("runtime", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("homepage", sa.String(length=500), nullable=True),
        sa.Column("number_of_seasons", sa.Integer(), nullable=True),
        sa.Column("number_of_episodes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_type", "tmdb_id", name="uq_content_type_tmdb_id"),
    )
    op.create_index(op.f("ix_contents_content_type"), "contents", ["content_type"], unique=False)
    op.create_index(op.f("ix_contents_tmdb_id"), "contents", ["tmdb_id"], unique=False)
    op.create_index(op.f("ix_contents_title"), "contents", ["title"], unique=False)
    op.create_index(
        "ix_contents_type_popularity", "contents", ["content_type", "popularity"], unique=False
    )
    op.create_index(
        "ix_contents_type_release_date", "contents", ["content_type", "release_date"], unique=False
    )

    # 2. Normalized Genres
    op.create_table(
        "genres",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tmdb_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_genres_tmdb_id"), "genres", ["tmdb_id"], unique=True)
    op.create_index(op.f("ix_genres_name"), "genres", ["name"], unique=True)

    op.create_table(
        "content_genres",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("genre_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["genre_id"], ["genres.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "genre_id", name="uq_content_genre"),
    )
    op.create_index(op.f("ix_content_genres_content_id"), "content_genres", ["content_id"], unique=False)
    op.create_index(op.f("ix_content_genres_genre_id"), "content_genres", ["genre_id"], unique=False)

    # 3. Normalized Languages
    op.create_table(
        "languages",
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("english_name", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "content_languages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["language_code"], ["languages.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "language_code", name="uq_content_language"),
    )
    op.create_index(op.f("ix_content_languages_content_id"), "content_languages", ["content_id"], unique=False)
    op.create_index(op.f("ix_content_languages_language_code"), "content_languages", ["language_code"], unique=False)

    # 4. Normalized People (Cast & Crew)
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("profile_path", sa.String(length=500), nullable=True),
        sa.Column("known_for_department", sa.String(length=100), nullable=True),
        sa.Column("popularity", sa.Float(), nullable=True, server_default="0.0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tmdb_id"),
    )
    op.create_index(op.f("ix_people_tmdb_id"), "people", ["tmdb_id"], unique=True)
    op.create_index(op.f("ix_people_name"), "people", ["name"], unique=False)

    op.create_table(
        "content_cast",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("character", sa.String(length=500), nullable=True),
        sa.Column("cast_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "person_id", "character", name="uq_content_cast_member"),
    )
    op.create_index(op.f("ix_content_cast_content_id"), "content_cast", ["content_id"], unique=False)
    op.create_index(op.f("ix_content_cast_person_id"), "content_cast", ["person_id"], unique=False)

    op.create_table(
        "content_crew",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("job", sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "person_id", "department", "job", name="uq_content_crew_member"),
    )
    op.create_index(op.f("ix_content_crew_content_id"), "content_crew", ["content_id"], unique=False)
    op.create_index(op.f("ix_content_crew_person_id"), "content_crew", ["person_id"], unique=False)

    # 5. External IDs and Videos
    op.create_table(
        "content_external_ids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "provider", name="uq_content_external_id_provider"),
    )
    op.create_index(op.f("ix_content_external_ids_content_id"), "content_external_ids", ["content_id"], unique=False)

    op.create_table(
        "content_videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("site", sa.String(length=100), nullable=False, server_default="YouTube"),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False, server_default="Trailer"),
        sa.Column("official", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "key", name="uq_content_video_key"),
    )
    op.create_index(op.f("ix_content_videos_content_id"), "content_videos", ["content_id"], unique=False)

    # 6. Saved Content (replacing favorites)
    op.create_table(
        "saved_content",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_id", name="uq_user_content_saved"),
    )
    op.create_index(op.f("ix_saved_content_content_id"), "saved_content", ["content_id"], unique=False)
    op.create_index(op.f("ix_saved_content_user_id"), "saved_content", ["user_id"], unique=False)

    # 7. Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reviews_content_id"), "reviews", ["content_id"], unique=False)
    op.create_index(op.f("ix_reviews_user_id"), "reviews", ["user_id"], unique=False)

    # 8. Content Embeddings & User Embeddings
    op.create_table(
        "content_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("model_name", sa.String(length=150), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id"),
    )
    op.create_index(op.f("ix_content_embeddings_content_hash"), "content_embeddings", ["content_hash"], unique=False)
    op.create_index(op.f("ix_content_embeddings_content_id"), "content_embeddings", ["content_id"], unique=True)

    op.create_table(
        "user_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("model_name", sa.String(length=150), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_embeddings_user_id"), "user_embeddings", ["user_id"], unique=True)

    # 9. Recommendation persistence
    op.create_table(
        "recommendation_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recommendation_candidates_content_id"), "recommendation_candidates", ["content_id"], unique=False)
    op.create_index(op.f("ix_recommendation_candidates_user_id"), "recommendation_candidates", ["user_id"], unique=False)

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recommendations_content_id"), "recommendations", ["content_id"], unique=False)
    op.create_index(op.f("ix_recommendations_user_id"), "recommendations", ["user_id"], unique=False)

    # 10. Interaction Events
    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_value", sa.Float(), nullable=True),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_interaction_events_content_id"), "interaction_events", ["content_id"], unique=False)
    op.create_index(op.f("ix_interaction_events_created_at"), "interaction_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_interaction_events_event_type"), "interaction_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_interaction_events_user_id"), "interaction_events", ["user_id"], unique=False)

    # 11. Safe Data Migration from legacy tables if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "movies" in tables:
        # Migrate movies to contents
        op.execute(
            """
            INSERT INTO contents (
                id, content_type, tmdb_id, title, overview, release_date,
                poster_path, backdrop_path, vote_average, vote_count,
                popularity, runtime, status, tagline, created_at, updated_at
            )
            SELECT
                id, 'movie', tmdb_id, title, overview, release_date,
                poster_path, backdrop_path, vote_average, vote_count,
                popularity, runtime, status, tagline, created_at, updated_at
            FROM movies
            ON CONFLICT (content_type, tmdb_id) DO NOTHING;
            """
        )

    if "favorites" in tables:
        op.execute(
            """
            INSERT INTO saved_content (user_id, content_id, created_at)
            SELECT user_id, movie_id, created_at
            FROM favorites
            ON CONFLICT (user_id, content_id) DO NOTHING;
            """
        )

    if "movie_embeddings" in tables:
        op.execute(
            """
            INSERT INTO content_embeddings (
                content_id, embedding, model_name, dimension, content_hash, model_version, created_at, updated_at
            )
            SELECT
                movie_id, embedding, model_name, dimension, content_hash, model_version, created_at, updated_at
            FROM movie_embeddings
            ON CONFLICT (content_id) DO NOTHING;
            """
        )

    # 12. Update Foreign Keys on ratings and watch_history to point to contents.id
    if "ratings" in tables:
        # Drop old constraint if referencing movies
        fks = inspector.get_foreign_keys("ratings")
        for fk in fks:
            if fk.get("referred_table") == "movies":
                op.drop_constraint(fk["name"], "ratings", type_="foreignkey")
        # Add new constraint to contents
        try:
            op.alter_column("ratings", "movie_id", new_column_name="content_id")
        except Exception:
            pass
        op.create_foreign_key(
            "fk_ratings_contents", "ratings", "contents", ["content_id"], ["id"], ondelete="CASCADE"
        )

    if "watch_history" in tables:
        fks = inspector.get_foreign_keys("watch_history")
        for fk in fks:
            if fk.get("referred_table") == "movies":
                op.drop_constraint(fk["name"], "watch_history", type_="foreignkey")
        try:
            op.alter_column("watch_history", "movie_id", new_column_name="content_id")
        except Exception:
            pass
        op.create_foreign_key(
            "fk_watch_history_contents", "watch_history", "contents", ["content_id"], ["id"], ondelete="CASCADE"
        )

    # Drop old obsolete tables if they exist
    if "favorites" in tables:
        op.drop_table("favorites")
    if "movie_embeddings" in tables:
        op.drop_table("movie_embeddings")
    if "movies" in tables:
        op.drop_table("movies")


def downgrade() -> None:
    op.drop_table("interaction_events")
    op.drop_table("recommendations")
    op.drop_table("recommendation_candidates")
    op.drop_table("user_embeddings")
    op.drop_table("content_embeddings")
    op.drop_table("reviews")
    op.drop_table("saved_content")
    op.drop_table("content_videos")
    op.drop_table("content_external_ids")
    op.drop_table("content_crew")
    op.drop_table("content_cast")
    op.drop_table("people")
    op.drop_table("content_languages")
    op.drop_table("languages")
    op.drop_table("content_genres")
    op.drop_table("genres")
    op.drop_table("contents")
