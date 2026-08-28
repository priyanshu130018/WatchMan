import { api } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import type {
  HomeResponse,
  Movie,
  Paginated,
  SearchFilters,
} from "@/types/movie";

export const moviesService = {
  home: async (): Promise<HomeResponse> => {
    const { data } = await api.get<HomeResponse>(endpoints.home);
    return data;
  },
  detail: async (id: string | number): Promise<Movie> => {
    const { data } = await api.get<Movie>(endpoints.movie(id));
    return data;
  },
  search: async (params: SearchFilters): Promise<Paginated<Movie>> => {
    const { data } = await api.get<Paginated<Movie>>(endpoints.search, {
      params,
    });
    return data;
  },
};
