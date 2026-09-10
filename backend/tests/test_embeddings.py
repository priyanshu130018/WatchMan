import unittest
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.database.session import SessionLocal
from app.database.models.movie import Movie
from app.database.models.movie_embedding import MovieEmbedding
from app.ml.embeddings.service import MovieEmbeddingService, MODEL_NAME, EXPECTED_DIMENSION


class TestEmbeddingServiceAndPgvector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        
        # Sync a cluster of test movies via the sync endpoint
        test_movie_ids = [550, 807, 680, 603, 27205, 157336, 155]
        for mid in test_movie_ids:
            try:
                cls.client.post('/api/movies/sync', json={'movie_id': mid})
            except Exception as e:
                print(f'Sync warning for {mid}: {e}')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

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

    def test_03_single_movie_embed_and_idempotency(self):
        rec1 = MovieEmbeddingService.embed_movie(self.db, movie_id=550)
        self.assertEqual(rec1.movie_id, 550)
        self.assertEqual(rec1.dimension, 384)
        self.assertEqual(rec1.model_name, MODEL_NAME)
        self.assertIsNotNone(rec1.content_hash)
        
        count_before = self.db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == 550).count()
        self.assertEqual(count_before, 1)

        rec2 = MovieEmbeddingService.embed_movie(self.db, movie_id=550, force=False)
        count_after = self.db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == 550).count()
        self.assertEqual(count_after, 1)
        self.assertEqual(rec1.content_hash, rec2.content_hash)

    def test_04_stale_embedding_detection(self):
        movie = self.db.query(Movie).filter(Movie.id == 550).first()
        self.assertIsNotNone(movie)
        
        old_emb = self.db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == 550).first()
        old_hash = old_emb.content_hash

        original_tagline = movie.tagline
        try:
            movie.tagline = 'Updated test tagline for stale embedding verification.'
            self.db.commit()
            
            updated_emb = MovieEmbeddingService.embed_movie(self.db, movie_id=550, force=False)
            self.assertNotEqual(updated_emb.content_hash, old_hash)
        finally:
            movie.tagline = original_tagline
            self.db.commit()
            MovieEmbeddingService.embed_movie(self.db, movie_id=550, force=True)

    def test_05_batch_embedding_all_synced_movies(self):
        batch_result = MovieEmbeddingService.batch_embed_movies(self.db, limit=50, batch_size=10)
        self.assertEqual(batch_result['status'], 'success')

    def test_06_pgvector_similarity_search(self):
        results = MovieEmbeddingService.search_similar_movies(self.db, movie_id=550, limit=5)
        
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        
        for item in results:
            self.assertNotEqual(item['movie']['id'], 550)
            self.assertIn('similarity', item)
            self.assertGreaterEqual(item['similarity'], 0.0)
            self.assertLessEqual(item['similarity'], 1.0)

        scores = [item['similarity'] for item in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_07_api_single_movie_embedding(self):
        response = self.client.post('/api/ml/embeddings/movies/550')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['movie_id'], 550)
        self.assertEqual(data['dimension'], 384)
        self.assertEqual(data['model'], MODEL_NAME)

    def test_08_api_batch_movie_embedding(self):
        response = self.client.post('/api/ml/embeddings/movies/batch', json={'limit': 20, 'batch_size': 10})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')

    def test_09_api_similar_movies(self):
        response = self.client.get('/api/movies/550/similar?limit=5')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['movie_id'], 550)
        self.assertIn('results', data)
        self.assertGreater(len(data['results']), 0)
        
        first = data['results'][0]
        self.assertIn('movie', first)
        self.assertIn('similarity', first)
        self.assertNotEqual(first['movie']['id'], 550)

    def test_10_missing_movie_error(self):
        response = self.client.post('/api/ml/embeddings/movies/999999999')
        self.assertEqual(response.status_code, 404)

        response_sim = self.client.get('/api/movies/999999999/similar')
        self.assertEqual(response_sim.status_code, 404)


if __name__ == '__main__':
    unittest.main()
