import { api } from "@/lib/api";
import { normalizeMovie, type Movie, type RecommendationMovie } from "@/types/movie";

export interface RecommendationListResponse {
  items: RecommendationMovie[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RecommendationParams {
  contentType?: "all" | "movie" | "tv";
  limit?: number;
  page?: number;
  forceRefresh?: boolean;
}

export const recommendationService = {
  getRecommendations: async (
    params?: RecommendationParams,
  ): Promise<RecommendationListResponse> => {
    const { data } = await api.get("/recommendations", {
      params: {
        content_type:
          params?.contentType && params.contentType !== "all" ? params.contentType : undefined,
        limit: params?.limit ?? 20,
        page: params?.page ?? 1,
        force_refresh: params?.forceRefresh ?? false,
      },
    });

    const items = Array.isArray(data?.items) ? data.items : [];
    const normalizedItems = items.map((item: unknown) => {
      const normalized = normalizeMovie(item);
      const raw = item as Record<string, unknown>;
      return {
        ...normalized,
        recommendation_score: Number(raw?.score ?? raw?.recommendation_score ?? 0),
        content_score: Number(raw?.content_score ?? 0),
        collaborative_score: Number(raw?.collaborative_score ?? 0),
        popularity_score: Number(raw?.popularity_score ?? 0),
        reason: String(raw?.explanation ?? raw?.reason ?? "Recommended for you"),
        sources: Array.isArray(raw?.sources) ? (raw.sources as string[]).map(String) : [],
      } as RecommendationMovie;
    });

    return {
      items: normalizedItems,
      total: Number(data?.total ?? normalizedItems.length),
      page: Number(data?.page ?? 1),
      page_size: Number(data?.page_size ?? normalizedItems.length),
      total_pages: Number(data?.total_pages ?? 1),
    };
  },

  personalized: async (limit = 20): Promise<RecommendationMovie[]> => {
    const { data } = await api.get("/recommendations/personalized", { params: { limit } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((item: unknown) => {
      const normalized = normalizeMovie(item);
      const raw = item as Record<string, unknown>;
      return {
        ...normalized,
        recommendation_score: Number(raw?.recommendation_score ?? raw?.score ?? 0),
        content_score: Number(raw?.content_score ?? 0),
        collaborative_score: Number(raw?.collaborative_score ?? 0),
        popularity_score: Number(raw?.popularity_score ?? 0),
        reason: String(raw?.reason ?? raw?.explanation ?? "Recommended for you"),
      } as RecommendationMovie;
    });
  },

  refresh: async (): Promise<{ status: string; message: string }> => {
    const { data } = await api.post("/recommendations/refresh");
    return data;
  },

  getSimilarContent: async (
    contentType: "movie" | "tv",
    tmdbId: number,
    limit = 10,
  ): Promise<Movie[]> => {
    const { data } = await api.get(`/recommendations/${contentType}/${tmdbId}`, {
      params: { limit },
    });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((item: unknown) => normalizeMovie(item));
  },
};
