import pandas as pd


class CollaborativeFiltering:

    def recommend(
        self,
        ratings: pd.DataFrame,
        user_id,
        top_k=20,
    ):

        watched = ratings[
            ratings.user_id == user_id
        ]["movie_id"]

        movies = (
            ratings.groupby("movie_id")
            .rating.mean()
            .sort_values(
                ascending=False
            )
        )

        return movies[
            ~movies.index.isin(watched)
        ].head(top_k)