from app.services.tmdb.service import TMDBService


class RecommendationService:

    def __init__(self):
        self.tmdb = TMDBService()

    async def trending(self):
        return await self.tmdb.trending_movies()

    async def popular(self):
        return await self.tmdb.popular_movies()

    async def top_rated(self):
        return await self.tmdb.top_rated_movies()

    async def similar(self, movie_id: int):
        return await self.tmdb.similar_movies(movie_id)

    async def recommend_from_movie(self, movie_id: int):
        return await self.tmdb.recommendations(movie_id)

    async def search(self, query: str, page: int = 1):
        return await self.tmdb.search_movies(
            query=query,
            page=page,
        )