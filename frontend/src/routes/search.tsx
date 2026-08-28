import { createFileRoute } from "@tanstack/react-router";
import { SearchPage } from "@/features/search/SearchPage";

export interface SearchSearch {
  q?: string;
  genre?: string;
  language?: string;
  platform?: string;
  year?: string;
  sort?: "popularity" | "latest" | "imdb" | "rabbit";
}

export const Route = createFileRoute("/search")({
  validateSearch: (search: Record<string, unknown>): SearchSearch => ({
    q: typeof search.q === "string" ? search.q : undefined,
    genre: typeof search.genre === "string" ? search.genre : undefined,
    language: typeof search.language === "string" ? search.language : undefined,
    platform: typeof search.platform === "string" ? search.platform : undefined,
    year: typeof search.year === "string" ? search.year : undefined,
    sort:
      search.sort === "popularity" ||
      search.sort === "latest" ||
      search.sort === "imdb" ||
      search.sort === "rabbit"
        ? search.sort
        : undefined,
  }),
  component: SearchPage,
});
