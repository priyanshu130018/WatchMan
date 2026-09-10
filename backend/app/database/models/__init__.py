from app.database.models.user import User
from app.database.models.profile import Profile
from app.database.models.movie import Movie
from app.database.models.favorite import Favorite
from app.database.models.rating import Rating
from app.database.models.watch_history import WatchHistory
from app.database.models.search_history import SearchHistory
from app.database.models.user_activity import UserActivity
from app.database.models.user_preference import UserPreference
from app.database.models.movie_embedding import MovieEmbedding
from app.database.models.recommendation_cache import RecommendationCache

__all__ = [
    "User",
    "Profile",
    "Movie",
    "Favorite",
    "Rating",
    "WatchHistory",
    "SearchHistory",
    "UserActivity",
    "UserPreference",
    "MovieEmbedding",
    "RecommendationCache",
]
