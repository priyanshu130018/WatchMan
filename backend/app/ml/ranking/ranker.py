from app.ml.ranking.scorer import (
    ScoreCalculator,
)


class Ranker:

    def __init__(self):

        self.scorer = ScoreCalculator()

    def rank(self, movies):

        return sorted(
            movies,
            key=lambda m: self.scorer.calculate(
                m["content_score"],
                m["collaborative_score"],
                m["popularity"],
            ),
            reverse=True,
        )