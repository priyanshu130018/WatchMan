import { createFileRoute } from "@tanstack/react-router";
import { SearchPage } from "@/features/Search";

export interface SearchRouteParams {
  q?: string;
  type?: "all" | "movie" | "tv";
  genre_id?: number;
  year?: number;
  sort?: string;
  page?: number;
}

export const Route = createFileRoute("/search")({
  validateSearch: (search: Record<string, unknown>): SearchRouteParams => ({
    q: typeof search.q === "string" ? search.q : undefined,
    type:
      search.type === "movie" || search.type === "tv" || search.type === "all"
        ? search.type
        : undefined,
    genre_id: search.genre_id ? Number(search.genre_id) : undefined,
    year: search.year ? Number(search.year) : undefined,
    sort: typeof search.sort === "string" ? search.sort : undefined,
    page: search.page ? Number(search.page) : undefined,
  }),
  component: SearchPage,
});
