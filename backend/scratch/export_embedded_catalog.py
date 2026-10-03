import sys
import os
import csv
from collections import Counter
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.content import Content
from app.models.embedding import ContentEmbedding
from app.models.taxonomy import Genre, ContentGenre, Language, ContentLanguage

def main():
    db: Session = SessionLocal()

    # Query all embedded catalog items by joining ContentEmbedding with Content
    records = (
        db.query(Content, ContentEmbedding)
        .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
        .all()
    )

    rows = []
    for content, emb in records:
        # Extract genres
        genre_list = []
        for g in (content.genres or []):
            if hasattr(g, "genre") and hasattr(g.genre, "name") and g.genre.name:
                genre_list.append(g.genre.name.strip())
            elif isinstance(g, dict) and g.get("name"):
                genre_list.append(g["name"].strip())
        genres_str = ", ".join(sorted(genre_list)) if genre_list else "Unknown"

        # Format content type
        c_type_raw = (content.content_type or "").lower()
        if c_type_raw == "movie":
            c_type_display = "Movie"
        elif c_type_raw == "tv":
            c_type_display = "TV/Web-Series"
        else:
            c_type_display = content.content_type

        # Extract release year
        rel_date = (content.release_date or "").strip()
        rel_year = rel_date[:4] if len(rel_date) >= 4 and rel_date[:4].isdigit() else "N/A"

        # Check embedding exists and has data
        emb_exists = "YES" if (emb.embedding is not None and len(emb.embedding) > 0) else "NO"

        row = {
            "content_id": content.id,
            "content_type": c_type_display,
            "title": content.title,
            "original_title": content.original_title or content.title,
            "original_language": content.original_language or "unknown",
            "release_year": rel_year,
            "genres": genres_str,
            "embedding_model": emb.model_name or "BAAI/bge-small-en-v1.5",
            "embedding_dimension": emb.dimension or (len(emb.embedding) if emb.embedding else 384),
            "embedding_exists": emb_exists,
            "_raw_content_type": c_type_raw,
            "_raw_release_year": int(rel_year) if rel_year.isdigit() else None,
            "_genre_list": genre_list,
        }
        rows.append(row)

    # Sort by content type and title
    rows.sort(key=lambda x: (x["content_type"], (x["title"] or "").lower()))

    # File paths for CSV export
    csv_filename = "embedded_catalog_items.csv"
    csv_path_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_filename)
    csv_path_project_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), csv_filename)

    fieldnames = [
        "content_id",
        "content_type",
        "title",
        "original_title",
        "original_language",
        "release_year",
        "genres",
        "embedding_model",
        "embedding_dimension",
        "embedding_exists",
    ]

    for out_path in [csv_path_backend, csv_path_project_root]:
        with open(out_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                csv_row = {k: r[k] for k in fieldnames}
                writer.writerow(csv_row)

    # Compute Summary
    total_embedded = len(rows)
    movies_count = sum(1 for r in rows if r["_raw_content_type"] == "movie")
    tv_count = sum(1 for r in rows if r["_raw_content_type"] == "tv")
    unique_languages = sorted(list(set(r["original_language"] for r in rows if r["original_language"])))
    
    all_genres = []
    for r in rows:
        all_genres.extend(r["_genre_list"])
    genre_counts = Counter(all_genres).most_common()

    valid_years = [r["_raw_release_year"] for r in rows if r["_raw_release_year"] is not None]
    earliest_year = min(valid_years) if valid_years else "N/A"
    latest_year = max(valid_years) if valid_years else "N/A"

    print("=" * 80)
    print("EMBEDDED CATALOG ITEMS SUMMARY")
    print("=" * 80)
    print(f"Total Embedded Items in DB : {total_embedded}")
    print(f"Movies Count               : {movies_count}")
    print(f"TV/Web-Series Count        : {tv_count}")
    print(f"Earliest Release Year      : {earliest_year}")
    print(f"Latest Release Year        : {latest_year}")
    print(f"Number of Unique Languages : {len(unique_languages)}")
    print(f"Unique Languages List      : {', '.join(unique_languages)}")
    print("\n--- Genre Distribution ---")
    for genre, count in genre_counts:
        pct = (count / total_embedded) * 100
        print(f"  - {genre:<25}: {count:4d} ({pct:5.1f}%)")

    print("\n" + "=" * 80)
    print(f"FIRST 50 ROWS (Exported to {csv_path_project_root})")
    print("=" * 80)
    header_fmt = "{:<5} | {:<14} | {:<32} | {:<6} | {:<5} | {:<35} | {:<23} | {:<4} | {:<6}"
    print(header_fmt.format("ID", "Type", "Title", "Lang", "Year", "Genres", "Model", "Dim", "Exists"))
    print("-" * 145)
    for idx, r in enumerate(rows[:50], start=1):
        title_disp = (r["title"][:29] + "...") if len(r["title"]) > 32 else r["title"]
        genres_disp = (r["genres"][:32] + "...") if len(r["genres"]) > 35 else r["genres"]
        model_disp = (r["embedding_model"][:20] + "...") if len(r["embedding_model"]) > 23 else r["embedding_model"]
        print(header_fmt.format(
            r["content_id"],
            r["content_type"],
            title_disp,
            r["original_language"],
            r["release_year"],
            genres_disp,
            model_disp,
            r["embedding_dimension"],
            r["embedding_exists"]
        ))

    db.close()

if __name__ == "__main__":
    main()
