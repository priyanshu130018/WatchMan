from app.services.tmdb.service import TMDBService


class SearchService:

    @staticmethod
    async def search_movies(query: str, page: int = 1):
        return await TMDBService.search_movies(
            query=query,
            page=page,
        )