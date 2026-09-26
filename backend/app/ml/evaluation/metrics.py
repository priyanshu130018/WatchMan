from math import log2
from typing import Sequence


def precision_at_k(recommended_ids: Sequence[int], relevant_ids: set[int] | Sequence[int], k: int = 10) -> float:
    """
    Computes Precision@K: (number of relevant items in top K) / K.
    """
    if k <= 0 or not recommended_ids or not relevant_ids:
        return 0.0

    rel_set = set(relevant_ids)
    top_k = list(recommended_ids)[:k]
    hits = sum(1 for item_id in top_k if item_id in rel_set)
    return round(hits / k, 4)


def recall_at_k(recommended_ids: Sequence[int], relevant_ids: set[int] | Sequence[int], k: int = 10) -> float:
    """
    Computes Recall@K: (number of relevant items in top K) / (total relevant items).
    """
    if k <= 0 or not recommended_ids or not relevant_ids:
        return 0.0

    rel_set = set(relevant_ids)
    if len(rel_set) == 0:
        return 0.0

    top_k = list(recommended_ids)[:k]
    hits = sum(1 for item_id in top_k if item_id in rel_set)
    return round(hits / len(rel_set), 4)


def hit_rate_at_k(recommended_ids: Sequence[int], relevant_ids: set[int] | Sequence[int], k: int = 10) -> float:
    """
    Computes Hit Rate@K: 1.0 if at least one relevant item appears in top K, else 0.0.
    """
    if k <= 0 or not recommended_ids or not relevant_ids:
        return 0.0

    rel_set = set(relevant_ids)
    top_k = list(recommended_ids)[:k]
    for item_id in top_k:
        if item_id in rel_set:
            return 1.0
    return 0.0


def mean_reciprocal_rank(recommended_ids: Sequence[int], relevant_ids: set[int] | Sequence[int]) -> float:
    """
    Computes Mean Reciprocal Rank (MRR): 1 / rank of first relevant item (1-indexed).
    """
    if not recommended_ids or not relevant_ids:
        return 0.0

    rel_set = set(relevant_ids)
    for idx, item_id in enumerate(recommended_ids, start=1):
        if item_id in rel_set:
            return round(1.0 / idx, 4)
    return 0.0


def ndcg_at_k(recommended_ids: Sequence[int], relevant_ids: set[int] | Sequence[int], k: int = 10) -> float:
    """
    Computes Normalized Discounted Cumulative Gain (NDCG@K) with binary relevance.
    """
    if k <= 0 or not recommended_ids or not relevant_ids:
        return 0.0

    rel_set = set(relevant_ids)
    if not rel_set:
        return 0.0

    top_k = list(recommended_ids)[:k]

    # Calculate DCG@K
    dcg = 0.0
    for idx, item_id in enumerate(top_k, start=1):
        if item_id in rel_set:
            dcg += 1.0 / log2(idx + 1)

    # Calculate IDCG@K (ideal DCG)
    ideal_hits = min(k, len(rel_set))
    idcg = sum(1.0 / log2(idx + 1) for idx in range(1, ideal_hits + 1))

    if idcg == 0.0:
        return 0.0

    return round(dcg / idcg, 4)


def catalog_coverage(all_recommended_ids: set[int] | Sequence[int], total_catalog_ids: set[int] | Sequence[int]) -> float:
    """
    Computes percentage of unique catalog items recommended across all users.
    """
    catalog_set = set(total_catalog_ids)
    if not catalog_set:
        return 0.0

    rec_set = set(all_recommended_ids)
    covered = rec_set.intersection(catalog_set)
    return round(len(covered) / len(catalog_set), 4)


def intra_list_diversity(items_genres: list[list[str]]) -> float:
    """
    Computes average pairwise Jaccard distance between item genre sets in the recommendation list.
    """
    if not items_genres or len(items_genres) < 2:
        return 0.0

    genre_sets = [set(g.strip().lower() for g in genres if g and isinstance(g, str)) for genres in items_genres]
    n = len(genre_sets)
    total_distance = 0.0
    pairs_count = 0

    for i in range(n):
        for j in range(i + 1, n):
            set_a = genre_sets[i]
            set_b = genre_sets[j]

            if not set_a and not set_b:
                dist = 0.0
            elif not set_a or not set_b:
                dist = 1.0
            else:
                intersection = len(set_a.intersection(set_b))
                union = len(set_a.union(set_b))
                jaccard_sim = intersection / union if union > 0 else 0.0
                dist = 1.0 - jaccard_sim

            total_distance += dist
            pairs_count += 1

    if pairs_count == 0:
        return 0.0

    return round(total_distance / pairs_count, 4)
