"""
Seed script to insert realistic staging catalog items for runtime verification.

Reads the database connection string from the DATABASE_URL environment variable
(the same variable the backend uses). There is intentionally NO hardcoded
fallback credential and NO localhost default: if DATABASE_URL is not set the
script exits with a clear error rather than silently connecting somewhere.
"""

import os
import sys

import psycopg


def _get_database_url() -> str:
    """Return DATABASE_URL from the environment or fail clearly.

    No fallback password and no localhost default — a missing DATABASE_URL is a
    configuration error, not something to paper over with a guessed connection.
    """
    url = os.environ.get("DATABASE_URL")
    if not url or not url.strip():
        sys.stderr.write(
            "ERROR: DATABASE_URL is not set. Export it (e.g. from backend/.env) "
            "before running the staging seed script. Refusing to continue "
            "without an explicit database connection string.\n"
        )
        sys.exit(1)
    # psycopg3 does not accept the SQLAlchemy '+psycopg' driver suffix.
    return url.strip().replace("+psycopg", "")


def seed_database():
    conn_str = _get_database_url()

    # Print only the host/db portion, never the credentials in the URL.
    print(f"Connecting to database: {conn_str.split('@')[-1]}")
    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                # 1. Insert Genres
                cur.execute("""
                    INSERT INTO genres (id, tmdb_id, name) VALUES
                    (1, 28, 'Action'),
                    (2, 18, 'Drama'),
                    (3, 878, 'Sci-Fi'),
                    (4, 53, 'Thriller')
                    ON CONFLICT (tmdb_id) DO NOTHING;
                """)

                # 2. Insert Movies
                cur.execute("""
                    INSERT INTO contents (
                        id, content_type, tmdb_id, title, original_title, overview,
                        release_date, poster_path, backdrop_path, popularity, vote_average,
                        vote_count, adult, runtime, status, tagline, created_at, updated_at
                    ) VALUES (
                        1, 'movie', 550, 'Fight Club', 'Fight Club',
                        'A ticking-time-bomb insomniac and a slippery soap salesman channel primal male aggression into a shocking new form of therapy.',
                        '1999-10-15', '/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg', '/hZkgoQYus5vegHoetLkCJzb17zJ.jpg',
                        85.5, 8.43, 27000, false, 139, 'Released', 'Mischief. Mayhem. Soap.', NOW(), NOW()
                    ), (
                        2, 'movie', 27205, 'Inception', 'Inception',
                        'Cobb, a skilled thief who steals corporate secrets through dream-sharing technology, is given the inverse task of planting an idea.',
                        '2010-07-15', '/oYuLEt3zVCKq57qu2F8dT7NIa6f.jpg', '/8ZTVqvKDQ8emSGUEMjsS4yHAwrp.jpg',
                        120.4, 8.36, 35000, false, 148, 'Released', 'Your mind is the scene of the crime.', NOW(), NOW()
                    ), (
                        3, 'tv', 1399, 'Game of Thrones', 'Game of Thrones',
                        'Seven noble families fight for control of the mythical land of Westeros.',
                        '2011-04-17', '/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg', '/2OMB0ynKlyIenMJWI2Dy9IWT4c.jpg',
                        150.0, 8.45, 23000, false, 60, 'Ended', 'Winter Is Coming', NOW(), NOW()
                    )
                    ON CONFLICT (content_type, tmdb_id) DO UPDATE SET popularity = EXCLUDED.popularity;
                """)

                # 3. Associate Genres
                cur.execute("""
                    INSERT INTO content_genres (content_id, genre_id) VALUES
                    (1, 2), (1, 4),
                    (2, 1), (2, 3), (2, 4),
                    (3, 1), (3, 2)
                    ON CONFLICT (content_id, genre_id) DO NOTHING;
                """)

                conn.commit()
                print("Seeding completed successfully: Genres, Movies (Fight Club, Inception), and TV (Game of Thrones).")
    except Exception as e:
        print(f"Seeding error: {e}")
        raise


if __name__ == "__main__":
    seed_database()
