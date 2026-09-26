from app.models.content import Content, ContentExternalId, ContentType, ContentVideo
from app.models.taxonomy import Genre, ContentGenre, Language, ContentLanguage
from app.models.people import Person, ContentCast, ContentCrew
from app.models.user import User, Profile, UserPreference
from app.models.review import Rating, Review
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent, SearchHistory
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.recommendation import (
    RecommendationCandidate,
    Recommendation,
    RecommendationCache,
)

# Backward-compatibility aliases
Movie = Content
Favorite = SavedContent
MovieEmbedding = ContentEmbedding

__all__ = [
    "Content",
    "ContentType",
    "ContentExternalId",
    "ContentVideo",
    "Genre",
    "ContentGenre",
    "Language",
    "ContentLanguage",
    "Person",
    "ContentCast",
    "ContentCrew",
    "User",
    "Profile",
    "UserPreference",
    "Rating",
    "Review",
    "SavedContent",
    "WatchHistory",
    "InteractionEvent",
    "SearchHistory",
    "ContentEmbedding",
    "UserEmbedding",
    "ALSUserFactors",
    "ALSItemFactors",
    "RecommendationCandidate",
    "Recommendation",
    "RecommendationCache",
    # Legacy aliases
    "Movie",
    "Favorite",
    "MovieEmbedding",
]
