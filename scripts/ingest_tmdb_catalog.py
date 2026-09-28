"""CLI script to ingest the broad TMDB catalogue for Movies and Web Series into WatchMan.

Features:
- Partitioned Discover queries across historical and modern release eras.
- Automatic partition subdivision when TMDB total_pages > 500 (avoiding HTTP 400).
- Rate limiting and bounded concurrency to respect TMDB API limits.
- Resumable checkpointing for fault-tolerant long-running imports.
- Dialect-aware bulk upsert (Postgres xmax=0 / SQLite fallback) for content,
  genres, and languages.
- Real database totals printed at completion.

Usage examples:
  python scripts/ingest_tmdb_catalog.py --estimate
  python scripts/ingest_tmdb_catalog.py --movies --max-pages-per-partition 10
  python scripts/ingest_tmdb_catalog.py --movies --tv --max-pages-per-partition 15
  python scripts/ingest_tmdb_catalog.py --resume
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import SessionLocal
from app.services.tmdb.importer import (
    DatePartition,
    TMDBImporter,
    get_initial_movie_partitions,
    get_initial_tv_partitions,
)
from app.services.tmdb.service import TMDBService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest broad TMDB movie and TV catalogue into WatchMan database."
    )
    parser.add_argument(
        "--movies",
        action="store_true",
        help="Ingest movie catalogue (default: both if neither --movies nor --tv specified)",
    )
    parser.add_argument(
        "--tv",
        action="store_true",
        help="Ingest TV/web-series catalogue (default: both if neither --movies nor --tv specified)",
    )
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="Dry-run estimation: plan partitions, check page 1 counts, and print overview without ingesting",
    )
    parser.add_argument(
        "--max-pages-per-partition",
        type=int,
        default=None,
        help="Maximum pages to ingest per partition (useful for staged imports, e.g. 15)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size for database upserts (default: 200)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent TMDB fetch workers (default: 4)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=4.0,
        help="Maximum TMDB requests per second (default: 4.0)",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from checkpoint file (default: True)",
    )
    parser.add_argument(
        "--checkpoint-file",
        type=str,
        default=".ingest_checkpoint.json",
        help="Checkpoint file path (default: .ingest_checkpoint.json)",
    )
    return parser.parse_args()


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse_args()

    include_movies = args.movies
    include_tv = args.tv
    if not include_movies and not include_tv:
        include_movies = True
        include_tv = True

    partitions: list[DatePartition] = []
    if include_movies:
        partitions.extend(get_initial_movie_partitions())
    if include_tv:
        partitions.extend(get_initial_tv_partitions())

    print("=================================================================")
    print(" WatchMan TMDB Catalogue Ingestion Pipeline")
    print("=================================================================")
    print(f"Modes: Movies={include_movies}, TV={include_tv}")
    print(f"Partitions Defined: {len(partitions)}")
    print(f"Max Pages / Partition: {args.max_pages_per_partition or 'Unlimited (<= 500)'}")
    print(f"Concurrency: {args.concurrency} | Rate Limit: {args.rate_limit} req/s")
    print(f"Resume: {args.resume} | Checkpoint: {args.checkpoint_file}")
    print(f"Dry Run Estimate: {args.estimate}")
    print("=================================================================\n")

    importer = TMDBImporter(
        db_factory=SessionLocal,
        tmdb_service=TMDBService(),
        rate_limit_rps=args.rate_limit,
        concurrency=args.concurrency,
        checkpoint_file=args.checkpoint_file,
        max_pages_per_partition=args.max_pages_per_partition,
        batch_size=args.batch_size,
        progress_callback=lambda msg: print(msg, flush=True),
    )

    summary = await importer.run(
        partitions=partitions,
        resume=args.resume,
        dry_run_estimate=args.estimate,
    )

    if args.estimate:
        print("\n--- Partition Plan Breakdown ---")
        for p in summary.get("planned_partitions", []):
            print(
                f"  [{p['type'].upper()}] {p['label']:<32} | "
                f"{p['start']} .. {p['end']} | "
                f"Est. Records: {p['total_results']:>7,} | Pages: {p['total_pages']:>4}"
            )
        print("---------------------------------")
        print(f"Total Leaf Partitions: {summary.get('partitions_count')}")
        print(f"Total TMDB Records:    {summary.get('estimated_tmdb_records', 0):,}")
        print(f"Total Discover Pages:  {summary.get('estimated_pages', 0):,}")
        print("Dry run completed. Run without --estimate to execute ingestion.")
    else:
        print("\n=================================================================")
        print(" Final Ingestion Report")
        print("=================================================================")
        print(f"Partitions Processed: {summary.get('partitions_processed', 0)}")
        print(f"New Records Inserted: {summary.get('inserted', 0):,}")
        print(f"Existing Updated:     {summary.get('updated', 0):,}")
        print(f"Database Movies:      {summary.get('db_total_movies', 0):,}")
        print(f"Database TV Shows:    {summary.get('db_total_tv', 0):,}")
        print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
