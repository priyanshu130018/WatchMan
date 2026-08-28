from app.ml.models.content_based import (
    ContentBasedModel,
)
from app.ml.pipelines.preprocess import (
    DataPreprocessor,
)


class Trainer:

    def __init__(self):

        self.model = ContentBasedModel()

    def train(self, csv_path):

        df = DataPreprocessor.load(csv_path)

        self.model.fit(df)

        return self.model