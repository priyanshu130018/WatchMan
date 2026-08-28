class Evaluator:

    @staticmethod
    def precision(recommended, relevant):

        hits = len(
            set(recommended) &
            set(relevant)
        )

        return hits / len(recommended)