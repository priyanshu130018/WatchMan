import { api } from '@/lib/api';
export type Favorite = { id: number; user_id: string; movie_id: number; created_at: string };
export type Watch = { id: number; user_id: string; movie_id: number; progress: number; watched_at: string };
export type Rating = { id: number; user_id: string; movie_id: number; rating: number; review?: string | null; updated_at: string };
export const userService = {
  favorites: async () => (await api.get<Favorite[]>('/favorites/')).data,
  addFavorite: async (movie_id: number) => (await api.post('/favorites/', { movie_id })).data,
  removeFavorite: async (movie_id: number) => (await api.delete(`/favorites/${movie_id}`)).data,
  history: async () => (await api.get<Watch[]>('/watch-history/')).data,
  addHistory: async (movie_id: number, progress = 0) => (await api.post('/watch-history/', { movie_id, progress })).data,
  updateHistory: async (id: number, progress: number) => (await api.put(`/watch-history/${id}`, { progress })).data,
  removeHistory: async (id: number) => (await api.delete(`/watch-history/${id}`)).data,
  ratings: async () => (await api.get<Rating[]>('/ratings/')).data,
  rateMovie: async (movieId: number, rating: number, review?: string) =>
    (await api.put<Rating>(`/ratings/${movieId}`, { rating, review })).data,
};
