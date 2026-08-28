import pandas as pd


class DataPreprocessor:

    @staticmethod
    def load(csv_path):

        df = pd.read_csv(csv_path)

        df.fillna("", inplace=True)

        return df