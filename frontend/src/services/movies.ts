import { api } from "@/lib/api";
import { normalizeMovie, type Movie } from "@/types/movie";

const list = async (path: string): Promise<Movie[]> => {
  const { data } = await api.get(path);
  const results = Array.isArray(data?.results) ? data.results : [];
  return results.map(normalizeMovie);
};
export const moviesService = {
  trending: () => list("/movies/trending"),
  popular: () => list("/movies/popular"),
  topRated: () => list("/movies/top-rated"),
  latest: () => list("/movies/latest"),
  search: async (query: string) => list(`/search/movies?query=${encodeURIComponent(query)}`),
  detail: async (id: number): Promise<Movie> => {
    const { data } = await api.get(`/movies/${id}`);
    return normalizeMovie(data);
  },
  similar: async (id: number): Promise<Movie[]> => {
    const { data } = await api.get(`/movies/${id}/similar?limit=12`);
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((item: unknown) =>
      normalizeMovie((item as { movie?: unknown }).movie ?? item),
    );
  },
};
