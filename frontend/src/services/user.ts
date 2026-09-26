import { api } from "@/lib/api";
import type {
  User,
  UserPreferences,
  SavedItem,
  RatingItem,
  ReviewItem,
  WatchHistoryItem,
} from "@/types/user";

export const userService = {
  // Profile
  getProfile: async (): Promise<User> => {
    const { data } = await api.get<User>("/users/me");
    return data;
  },

  updateProfile: async (payload: {
    full_name?: string;
    username?: string;
    avatar_url?: string;
  }): Promise<User> => {
    const { data } = await api.put<User>("/users/me", payload);
    return data;
  },

  // Preferences
  getPreferences: async (): Promise<UserPreferences> => {
    const { data } = await api.get<UserPreferences>("/users/me/preferences");
    return data;
  },

  updatePreferences: async (payload: {
    favorite_genres: number[];
    disliked_genres: number[];
  }): Promise<UserPreferences> => {
    const { data } = await api.put<UserPreferences>("/users/me/preferences", payload);
    return data;
  },

  // Saved / Favorites
  favorites: async (): Promise<SavedItem[]> => {
    const { data } = await api.get<SavedItem[]>("/saved");
    return data;
  },

  addFavorite: async (
    movieIdOrData:
      number | { content_type?: string; tmdb_id?: number; content_id?: number; movie_id?: number },
  ): Promise<SavedItem> => {
    const body = typeof movieIdOrData === "number" ? { movie_id: movieIdOrData } : movieIdOrData;
    const { data } = await api.post<SavedItem>("/saved", body);
    return data;
  },

  removeFavorite: async (
    movieIdOrContentType: number | string,
    tmdbId?: number,
  ): Promise<{ message: string }> => {
    if (typeof movieIdOrContentType === "string" && tmdbId !== undefined) {
      const { data } = await api.delete<{ message: string }>(
        `/saved/${movieIdOrContentType}/${tmdbId}`,
      );
      return data;
    }
    const { data } = await api.delete<{ message: string }>(`/saved/${movieIdOrContentType}`);
    return data;
  },

  // Ratings
  ratings: async (): Promise<RatingItem[]> => {
    const { data } = await api.get<RatingItem[]>("/ratings");
    return data;
  },

  getRatingForContent: async (contentType: string, tmdbId: number): Promise<RatingItem> => {
    const { data } = await api.get<RatingItem>(`/ratings/${contentType}/${tmdbId}`);
    return data;
  },

  rateMovie: async (movieId: number, rating: number, review?: string): Promise<RatingItem> => {
    const { data } = await api.put<RatingItem>(`/ratings/${movieId}`, { rating, review });
    return data;
  },

  rateContent: async (
    contentType: string,
    tmdbId: number,
    rating: number,
    review?: string,
  ): Promise<RatingItem> => {
    const { data } = await api.put<RatingItem>(`/ratings/${contentType}/${tmdbId}`, {
      rating,
      review,
    });
    return data;
  },

  deleteRating: async (
    contentTypeOrId: string | number,
    tmdbId?: number,
  ): Promise<{ message: string }> => {
    if (typeof contentTypeOrId === "string" && tmdbId !== undefined) {
      const { data } = await api.delete<{ message: string }>(
        `/ratings/${contentTypeOrId}/${tmdbId}`,
      );
      return data;
    }
    const { data } = await api.delete<{ message: string }>(`/ratings/${contentTypeOrId}`);
    return data;
  },

  // Reviews
  getReviews: async (
    contentType: string,
    tmdbId: number,
    page = 1,
    limit = 16,
  ): Promise<{ results: ReviewItem[]; total: number; page: number; total_pages: number }> => {
    const { data } = await api.get<{
      results: ReviewItem[];
      total: number;
      page: number;
      total_pages: number;
    }>(`/reviews/${contentType}/${tmdbId}?page=${page}&limit=${limit}`);
    return data;
  },

  createReview: async (payload: {
    content_type?: string;
    tmdb_id?: number;
    content_id?: number;
    title?: string;
    content: string;
    rating?: number;
  }): Promise<ReviewItem> => {
    const { data } = await api.post<ReviewItem>("/reviews", payload);
    return data;
  },

  updateReview: async (
    reviewId: number,
    payload: { title?: string; content?: string; rating?: number },
  ): Promise<ReviewItem> => {
    const { data } = await api.put<ReviewItem>(`/reviews/${reviewId}`, payload);
    return data;
  },

  deleteReview: async (reviewId: number): Promise<{ message: string }> => {
    const { data } = await api.delete<{ message: string }>(`/reviews/${reviewId}`);
    return data;
  },

  // Watch History
  history: async (): Promise<WatchHistoryItem[]> => {
    const { data } = await api.get<WatchHistoryItem[]>("/watch-history");
    return data;
  },

  addHistory: async (
    movieIdOrData:
      | number
      | {
          content_type?: string;
          tmdb_id?: number;
          content_id?: number;
          movie_id?: number;
          progress?: number;
          completed?: boolean;
        },
    progress = 0,
  ): Promise<WatchHistoryItem> => {
    const body =
      typeof movieIdOrData === "number" ? { movie_id: movieIdOrData, progress } : movieIdOrData;
    const { data } = await api.post<WatchHistoryItem>("/watch-history", body);
    return data;
  },

  updateHistory: async (
    id: number,
    progress: number,
    completed?: boolean,
  ): Promise<WatchHistoryItem> => {
    const { data } = await api.put<WatchHistoryItem>(`/watch-history/${id}`, {
      progress,
      completed,
    });
    return data;
  },

  removeHistory: async (id: number): Promise<{ message: string }> => {
    const { data } = await api.delete<{ message: string }>(`/watch-history/${id}`);
    return data;
  },
};
