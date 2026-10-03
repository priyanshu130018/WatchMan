from app.db.session import SessionLocal
from app.models.user import User, UserPreference
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.ranking.hybrid import HybridRanker
from app.models.content import Content

db = SessionLocal()
try:
    aryan = db.query(User).filter(User.username == "aryan").first()
    pref = db.query(UserPreference).filter(UserPreference.user_id == aryan.id).first()
    print("Aryan favorite genres:", pref.favorite_genres if pref else None)

    seen = CandidatePipeline.get_user_seen_content_ids(db, aryan.id)
    als_cands = ALSCollaborativeCandidateGenerator.generate_candidates(db, aryan.id, limit=10, exclude_content_ids=seen)
    print("\n--- ARYAN ALS CANDIDATES ---")
    for c in als_cands:
        cnt = db.query(Content).filter(Content.id == c["content_id"]).first()
        genres = [g.genre.name for g in cnt.genres if hasattr(g, "genre") and hasattr(g.genre, "name")] if cnt else []
        print(f"ALS cand ID={c['content_id']}, score={c['score']}, title={cnt.title if cnt else None}, genres={genres}")

    # Inspect preference scoring
    pref_genres, pref_langs = HybridRanker.get_user_profile_preferences(db, aryan.id)
    print("\nHybridRanker parsed genres:", pref_genres, "langs:", pref_langs)

    all_cands = CandidatePipeline.generate_all_candidates(db, aryan.id, limit_per_channel=30)
    # Check if any candidate has multiple sources
    multi_source = [c for c in all_cands if len(c.sources) > 1]
    print(f"\nCandidates with multiple sources: {len(multi_source)} / {len(all_cands)}")
    for m in multi_source[:5]:
        print(f"ID={m.content_id}, title={m.content.title if m.content else None}, sources={m.sources}, content_score={m.content_score}, collab_score={m.collaborative_score}, pop_score={m.popularity_score}, fresh_score={m.freshness_score}")

    ranked = HybridRanker.rank_candidates(db, aryan.id, all_cands, limit=20)
    print("\n--- TOP 20 RANKED FOR ARYAN ---")
    for r in ranked:
        print(f"Rank {r.rank:2d}: score={r.score:.4f} (cb={r.content_score:.4f}, als={r.collaborative_score:.4f}, pop={r.popularity_score:.4f}, fresh={r.freshness_score:.4f}, pref={r.preference_score:.4f}) | {r.content.title} | {r.sources}")

finally:
    db.close()
