import { api } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import type { Movie } from "@/types/movie";

export const historyService = {
  list: async (): Promise<Movie[]> => {
    const { data } = await api.get<Movie[] | { results: Movie[] }>(
      endpoints.history,
    );
    return Array.isArray(data) ? data : data.results;
  },
  clear: async (): Promise<void> => {
    await api.delete(endpoints.history);
  },
};
