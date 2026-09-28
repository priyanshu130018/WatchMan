import { createFileRoute } from "@tanstack/react-router";
import { SearchPage } from "@/features/Search";

export interface SearchRouteParams {
  q?: string;
  type?: "all" | "movie" | "tv";
  genre_id?: number;
  genre?: number;
  language?: string;
  year?: number;
  sort?: string;
  page?: number;
}

export const Route = createFileRoute("/search")({
  validateSearch: (search: Record<string, unknown>): SearchRouteParams => {
    const rawGenre = search.genre_id ?? search.genre;
    const genreId = rawGenre ? Number(rawGenre) : undefined;
    return {
      q: typeof search.q === "string" ? search.q : undefined,
      type:
        search.type === "movie" || search.type === "tv" || search.type === "all"
          ? search.type
          : undefined,
      genre_id: genreId,
      genre: genreId,
      language: typeof search.language === "string" ? search.language : undefined,
      year: search.year ? Number(search.year) : undefined,
      sort: typeof search.sort === "string" ? search.sort : undefined,
      page: search.page ? Number(search.page) : undefined,
    };
  },
  component: SearchPage,
});
