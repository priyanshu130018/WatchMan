from app.ml.ranking.ranker import Ranker


class HybridRecommender:

    def __init__(self):

        self.ranker = Ranker()

    def recommend(self, movies):

        return self.ranker.rank(movies)