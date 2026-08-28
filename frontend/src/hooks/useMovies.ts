import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { moviesService } from "@/services/movies";
import { favoritesService } from "@/services/favorites";
import { historyService } from "@/services/history";
import type { SearchFilters } from "@/types/movie";

export const qk = {
  home: ["home"] as const,
  movie: (id: string | number) => ["movie", String(id)] as const,
  search: (f: SearchFilters) => ["search", f] as const,
  favorites: ["favorites"] as const,
  history: ["history"] as const,
  profile: ["profile"] as const,
};

export function useHome() {
  return useQuery({ queryKey: qk.home, queryFn: moviesService.home });
}

export function useMovie(id: string | number | undefined) {
  return useQuery({
    queryKey: qk.movie(id ?? ""),
    queryFn: () => moviesService.detail(id!),
    enabled: Boolean(id),
  });
}

export function useSearch(filters: SearchFilters) {
  return useQuery({
    queryKey: qk.search(filters),
    queryFn: () => moviesService.search(filters),
    enabled: Boolean(filters.q && filters.q.length > 0),
  });
}

export function useFavorites() {
  return useQuery({ queryKey: qk.favorites, queryFn: favoritesService.list });
}

export function useHistory() {
  return useQuery({ queryKey: qk.history, queryFn: historyService.list });
}

export function useToggleFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      isFavorite,
    }: {
      id: string | number;
      isFavorite: boolean;
    }) => {
      if (isFavorite) await favoritesService.remove(id);
      else await favoritesService.add(id);
    },
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: qk.favorites });
      qc.invalidateQueries({ queryKey: qk.movie(vars.id) });
    },
  });
}

export function useClearHistory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: historyService.clear,
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.history }),
  });
}
