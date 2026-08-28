from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd


class ContentBasedModel:

    def __init__(self):

        self.movies = None
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=10000,
        )

        self.similarity = None

    def fit(self, dataframe: pd.DataFrame):

        self.movies = dataframe.fillna("")

        self.movies["features"] = (
            self.movies["title"]
            + " "
            + self.movies["genres"]
            + " "
            + self.movies["overview"]
        )

        matrix = self.vectorizer.fit_transform(
            self.movies["features"]
        )

        self.similarity = cosine_similarity(matrix)

    def recommend(self, title, k=10):

        idx = self.movies[
            self.movies.title.str.lower() == title.lower()
        ].index

        if len(idx) == 0:
            return []

        idx = idx[0]

        scores = list(
            enumerate(self.similarity[idx])
        )

        scores = sorted(
            scores,
            key=lambda x: x[1],
            reverse=True,
        )[1:k + 1]

        return self.movies.iloc[
            [i for i, _ in scores]
        ]