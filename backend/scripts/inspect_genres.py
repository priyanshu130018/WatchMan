from app.db.session import SessionLocal
from app.models.taxonomy import Genre
from app.models.user import UserPreference, User

db = SessionLocal()
try:
    genres = db.query(Genre).all()
    genre_map = {g.id: g.name for g in genres}
    genre_tmdb_map = {g.tmdb_id: g.name for g in genres if g.tmdb_id}
    print("Total genres in DB:", len(genres))
    print("Genre ID map sample:", list(genre_map.items())[:5])
    print("Genre TMDB map sample:", list(genre_tmdb_map.items())[:5])

    for p in db.query(UserPreference).all():
        u = db.query(User).filter(User.id == p.user_id).first()
        uname = u.username if u else "unknown"
        print(f"User {uname} ({p.user_id}): favorite_genres={p.favorite_genres}")
finally:
    db.close()
