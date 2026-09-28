#!/usr/bin/env python3
"""
Selective & On-Demand Content Embedding Backfill Script.

Supports targeted embedding generation strategies:
  --popular     : Embed top popular movies (~500) and top popular TV series (~500).
  --interacted  : Embed content referenced by real user activity (watch, save, rate, review, decision).
  --content-ids : Embed specific comma-separated content IDs.
  --all         : Gated full catalog backfill with explicit opt-in and warning.

Usage Examples:
  python scripts/backfill_content_embeddings.py --popular --limit 1000
  python scripts/backfill_content_embeddings.py --interacted
  python scripts/backfill_content_embeddings.py --content-ids 15,550,1234
  python scripts/backfill_content_embeddings.py --all --confirm-all
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules import cleanly
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content import Content
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.eligibility import ContentEmbeddingEligibilityService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_embeddings")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Selective & On-Demand Content Embedding Backfill for WatchMan."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--popular",
        action="store_true",
        help="Select top popular movies and TV series using catalog popularity ranking.",
    )
    group.add_argument(
        "--interacted",
        action="store_true",
        help="Embed only content items referenced by real user activity.",
    )
    group.add_argument(
        "--content-ids",
        type=str,
        default=None,
        help="Comma-separated list of explicit content IDs to embed (e.g. 15,550,1024).",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="DANGEROUS: Embed all missing contents across the entire catalog (requires --confirm-all).",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Total item limit for popular selection (default: 1000 = 500 movies + 500 TV series).",
    )
    parser.add_argument(
        "--popular-movie-limit",
        type=int,
        default=None,
        help="Explicit movie limit for popular mode (default from config: 500).",
    )
    parser.add_argument(
        "--popular-tv-limit",
        type=int,
        default=None,
        help="Explicit TV limit for popular mode (default from config: 500).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for vector encoding (default: 32).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-generation of embeddings even if content_hash and version match.",
    )
    parser.add_argument(
        "--confirm-all",
        action="store_true",
        help="Confirmation flag required when running --all.",
    )

    return parser.parse_args()


def run_popular_mode(db, args) -> dict:
    total_limit = args.limit or (
        settings.INITIAL_POPULAR_MOVIE_EMBED_LIMIT + settings.INITIAL_POPULAR_TV_EMBED_LIMIT
    )
    movie_limit = args.popular_movie_limit or (total_limit // 2)
    tv_limit = args.popular_tv_limit or (total_limit - movie_limit)

    logger.info(
        "Mode A: POPULAR selection (movie_limit=%d, tv_limit=%d, batch_size=%d)...",
        movie_limit,
        tv_limit,
        args.batch_size,
    )

    candidates = ContentEmbeddingEligibilityService.get_initial_popular_candidates(
        db=db,
        movie_limit=movie_limit,
        tv_limit=tv_limit,
    )
    logger.info("Found %d popular catalog candidates using real popularity ranking.", len(candidates))

    result = ContentEmbeddingService.batch_embed_items(
        db=db,
        contents=candidates,
        batch_size=args.batch_size,
        force=args.force,
    )
    return result


def run_interacted_mode(db, args) -> dict:
    logger.info("Mode B: INTERACTION-DRIVEN embedding...")
    interacted_ids = ContentEmbeddingEligibilityService.get_interacted_content_ids(db)
    logger.info("Found %d distinct content items referenced by real user interactions.", len(interacted_ids))

    if not interacted_ids:
        logger.info("No interacted content items found in database.")
        return {
            "status": "success",
            "total_candidates": 0,
            "to_embed": 0,
            "newly_created": 0,
            "updated": 0,
            "skipped_current": 0,
        }

    contents = db.query(Content).filter(Content.id.in_(interacted_ids)).all()
    result = ContentEmbeddingService.batch_embed_items(
        db=db,
        contents=contents,
        batch_size=args.batch_size,
        force=args.force,
    )
    return result


def run_content_ids_mode(db, args) -> dict:
    raw_ids = [s.strip() for s in args.content_ids.split(",") if s.strip()]
    content_ids = []
    for s in raw_ids:
        try:
            content_ids.append(int(s))
        except ValueError:
            logger.warning("Skipping invalid content ID: '%s'", s)

    logger.info("Mode C: EXPLICIT CONTENT IDs (%d requested)...", len(content_ids))
    if not content_ids:
        logger.error("No valid integer content IDs provided.")
        sys.exit(1)

    contents = db.query(Content).filter(Content.id.in_(content_ids)).all()
    found_ids = {c.id for c in contents}
    missing = set(content_ids) - found_ids
    if missing:
        logger.warning("Content IDs not found in catalog: %s", sorted(missing))

    result = ContentEmbeddingService.batch_embed_items(
        db=db,
        contents=contents,
        batch_size=args.batch_size,
        force=args.force,
    )
    return result


def run_all_mode(db, args) -> dict:
    print("=" * 72)
    print("WARNING: This will generate embeddings for the entire catalog.")
    print("WatchMan catalog contains thousands of records. Generating embeddings")
    print("for the whole catalog is computationally expensive and generally unnecessary.")
    print("=" * 72)

    if not args.confirm_all:
        if sys.stdin.isatty():
            confirm = input("Are you sure you want to embed the ENTIRE catalog? Type 'yes' to proceed: ")
            if confirm.strip().lower() != "yes":
                print("Aborted.")
                sys.exit(0)
        else:
            logger.error("--all requires --confirm-all in non-interactive environments.")
            sys.exit(1)

    logger.info("Proceeding with full catalog embedding backfill...")
    result = ContentEmbeddingService.batch_embed_contents(
        db=db,
        limit=args.limit,
        batch_size=args.batch_size,
        force=args.force,
    )
    return result


def main():
    args = parse_args()

    # Determine execution mode (default to --popular if none specified)
    mode = "popular"
    if args.interacted:
        mode = "interacted"
    elif args.content_ids:
        mode = "content_ids"
    elif args.all:
        mode = "all"
    elif args.popular:
        mode = "popular"

    db = SessionLocal()
    try:
        if mode == "popular":
            result = run_popular_mode(db, args)
        elif mode == "interacted":
            result = run_interacted_mode(db, args)
        elif mode == "content_ids":
            result = run_content_ids_mode(db, args)
        elif mode == "all":
            result = run_all_mode(db, args)
        else:
            logger.error("Unknown mode: %s", mode)
            sys.exit(1)

        print("-" * 72)
        print("Backfill Summary:")
        print(f"  * Mode              : {mode.upper()}")
        print(f"  * Total Candidates  : {result.get('total_candidates', 0)}")
        print(f"  * Skipped (Current) : {result.get('skipped_current', 0)}")
        print(f"  * Newly Created     : {result.get('newly_created', 0)}")
        print(f"  * Updated (Stale)   : {result.get('updated', 0)}")
        print("-" * 72)
    except Exception as exc:
        logger.exception("Content embedding backfill failed: %s", exc)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
