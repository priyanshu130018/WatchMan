class ScoreCalculator:

    def calculate(
        self,
        content_score,
        collaborative_score,
        popularity,
    ):

        return (
            0.45 * content_score
            + 0.35 * collaborative_score
            + 0.20 * popularity
        )