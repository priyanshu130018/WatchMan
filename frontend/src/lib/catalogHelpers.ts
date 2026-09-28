import type { ContentType } from "@/types/content";

export interface ListingFilterParams {
  page: number;
  genreId?: number;
  year?: number;
  language?: string;
  sort: string;
}

/**
 * Returns the query key for catalog listing.
 * Distinct activeMode ('popular' vs 'all') ensures React Query never conflates
 * popular and full catalogue responses.
 */
export function getContentListingQueryKey(
  contentType: ContentType,
  collection: string | undefined,
  filters: ListingFilterParams,
) {
  const activeMode = collection === "popular" ? "popular" : "all";
  return [contentType, "listing", activeMode, filters] as const;
}

/**
 * Computes the route detail path and resolved URL for content items.
 * - Movie content -> /movie/$id (resolved: /movie/{id})
 * - TV/Web Series -> /web-series/$id (resolved: /web-series/{id})
 */
export function getContentDetailRoute(content: {
  content_type: string;
  id: number | string;
  tmdb_id?: number | string;
}) {
  const isTv = content.content_type === "tv";
  const targetId = String(content.tmdb_id || content.id);
  const detailPath = isTv ? "/web-series/$id" : "/movie/$id";
  const resolvedUrl = isTv ? `/web-series/${targetId}` : `/movie/${targetId}`;
  return { isTv, targetId, detailPath, resolvedUrl };
}
