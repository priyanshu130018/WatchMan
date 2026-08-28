import { api } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import type { Movie } from "@/types/movie";

export const favoritesService = {
  list: async (): Promise<Movie[]> => {
    const { data } = await api.get<Movie[] | { results: Movie[] }>(
      endpoints.favorites,
    );
    return Array.isArray(data) ? data : data.results;
  },
  add: async (movieId: string | number): Promise<void> => {
    await api.post(endpoints.favorite(movieId));
  },
  remove: async (movieId: string | number): Promise<void> => {
    await api.delete(endpoints.favorite(movieId));
  },
};
