import unittest
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.ml.embeddings.service import MovieEmbeddingService, MODEL_NAME, EXPECTED_DIMENSION


class TestEmbeddingServiceAndPgvector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_embedding_dimension_and_norm(self):
        sample_text = 'A psychological thriller about an insomniac and underground fight club.'
        embedding = MovieEmbeddingService.generate_embedding(sample_text)
        
        self.assertEqual(len(embedding), 384)
        self.assertEqual(len(embedding), EXPECTED_DIMENSION)
        
        norm = np.linalg.norm(embedding)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_02_batch_embedding_dimensions(self):
        texts = [
            'Fight Club directed by David Fincher',
            'The Matrix sci-fi action cyberpunk',
            'Inception dream within a dream thriller'
        ]
        embeddings = MovieEmbeddingService.generate_embeddings_batch(texts)
        self.assertEqual(len(embeddings), 3)
        for emb in embeddings:
            self.assertEqual(len(emb), 384)


if __name__ == '__main__':
    unittest.main()
