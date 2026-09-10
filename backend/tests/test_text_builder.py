import unittest
from app.ml.embeddings.text_builder import build_movie_embedding_text, compute_movie_text_hash


class TestTextBuilder(unittest.TestCase):
    def setUp(self):
        self.complete_movie = {
            "title": "Fight Club",
            "tagline": "Mischief. Mayhem. Soap.",
            "overview": "An insomniac office worker looking for a way to change his life crosses paths with a devil-may-care soap maker.",
            "genres": [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}],
            "keywords": [{"id": 825, "name": "support group"}, {"id": 1465, "name": "underground fighting"}],
            "crew": [{"job": "Director", "name": "David Fincher"}, {"job": "Producer", "name": "Art Linson"}],
            "cast": [{"name": "Edward Norton"}, {"name": "Brad Pitt"}, {"name": "Helena Bonham Carter"}],
            "release_date": "1999-10-15",
            "runtime": 139
        }

    def test_complete_movie(self):
        text = build_movie_embedding_text(self.complete_movie)
        self.assertIn("Title: Fight Club", text)
        self.assertIn("Tagline: Mischief. Mayhem. Soap.", text)
        self.assertIn("Overview: An insomniac", text)
        self.assertIn("Genres: Drama, Thriller", text)
        self.assertIn("Keywords: support group, underground fighting", text)
        self.assertIn("Director: David Fincher", text)
        self.assertIn("Cast: Edward Norton, Brad Pitt, Helena Bonham Carter", text)
        self.assertIn("Year: 1999", text)
        self.assertIn("Runtime: 139 min", text)

    def test_missing_overview(self):
        movie = dict(self.complete_movie)
        movie["overview"] = None
        text = build_movie_embedding_text(movie)
        self.assertNotIn("Overview:", text)
        self.assertIn("Title: Fight Club", text)

    def test_missing_keywords(self):
        movie = dict(self.complete_movie)
        movie["keywords"] = []
        text = build_movie_embedding_text(movie)
        self.assertNotIn("Keywords:", text)
        self.assertIn("Title: Fight Club", text)

    def test_missing_cast(self):
        movie = dict(self.complete_movie)
        movie["cast"] = None
        text = build_movie_embedding_text(movie)
        self.assertNotIn("Cast:", text)
        self.assertIn("Title: Fight Club", text)

    def test_missing_director(self):
        movie = dict(self.complete_movie)
        movie["crew"] = [{"job": "Writer", "name": "Chuck Palahniuk"}]
        text = build_movie_embedding_text(movie)
        self.assertNotIn("Director:", text)
        self.assertIn("Title: Fight Club", text)

    def test_missing_genres(self):
        movie = dict(self.complete_movie)
        movie["genres"] = None
        text = build_movie_embedding_text(movie)
        self.assertNotIn("Genres:", text)
        self.assertIn("Title: Fight Club", text)

    def test_deterministic_hash(self):
        text1 = build_movie_embedding_text(self.complete_movie)
        text2 = build_movie_embedding_text(self.complete_movie)
        hash1 = compute_movie_text_hash(text1)
        hash2 = compute_movie_text_hash(text2)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)


if __name__ == "__main__":
    unittest.main()
