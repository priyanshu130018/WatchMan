import { api } from "@/lib/api";
import { normalizeMovie, type Movie, type RecommendationMovie } from "@/types/movie";
import { normalizeContentItem, type ContentItem } from "@/types/content";

export interface RecommendationListResponse {
  items: RecommendationMovie[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  is_cold_start?: boolean;
}

export interface RecommendationParams {
  contentType?: "all" | "movie" | "tv";
  limit?: number;
  page?: number;
  forceRefresh?: boolean;
}

export interface RecommendationSection {
  key: "must_like" | "watched_liked" | "continue_watching" | string;
  title: string;
  subtitle?: string;
  items: ContentItem[];
}

export interface HomeRecommendationsResponse {
  has_personalization: boolean;
  sections: RecommendationSection[];
}

export const recommendationService = {
  getHomeSections: async (params?: {
    limit?: number;
    forceRefresh?: boolean;
  }): Promise<HomeRecommendationsResponse> => {
    const { data } = await api.get("/recommendations/home", {
      params: {
        limit: params?.limit ?? 12,
        force_refresh: params?.forceRefresh ?? false,
      },
    });
    const sections = Array.isArray(data?.sections)
      ? data.sections.map((s: any) => ({
          key: String(s.key),
          title: String(s.title),
          subtitle: s.subtitle ? String(s.subtitle) : undefined,
          items: Array.isArray(s.items) ? s.items.map((it: any) => normalizeContentItem(it)) : [],
        }))
      : [];
    return {
      has_personalization: Boolean(data?.has_personalization && sections.length > 0),
      sections,
    };
  },

  getMustLike: async (params?: {
    limit?: number;
    forceRefresh?: boolean;
  }): Promise<{ key: string; title: string; items: ContentItem[] }> => {
    const { data } = await api.get("/recommendations/must-like", {
      params: {
        limit: params?.limit ?? 12,
        force_refresh: params?.forceRefresh ?? false,
      },
    });
    const items = Array.isArray(data?.items)
      ? data.items.map((it: any) => normalizeContentItem(it))
      : [];
    return {
      key: data?.key || "must_like",
      title: data?.title || "You Must Like",
      items,
    };
  },

  getWatchedLiked: async (params?: {
    limit?: number;
  }): Promise<{ key: string; title: string; items: ContentItem[] }> => {
    const { data } = await api.get("/recommendations/watched-liked", {
      params: { limit: params?.limit ?? 12 },
    });
    const items = Array.isArray(data?.items)
      ? data.items.map((it: any) => normalizeContentItem(it))
      : [];
    return {
      key: data?.key || "watched_liked",
      title: data?.title || "You Already Watched & Liked",
      items,
    };
  },

  getContinueWatching: async (params?: {
    limit?: number;
  }): Promise<{ key: string; title: string; items: ContentItem[] }> => {
    const { data } = await api.get("/recommendations/continue-watching", {
      params: { limit: params?.limit ?? 12 },
    });
    const items = Array.isArray(data?.items)
      ? data.items.map((it: any) => normalizeContentItem(it))
      : [];
    return {
      key: data?.key || "continue_watching",
      title: data?.title || "Continue Watching",
      items,
    };
  },

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
      is_cold_start: Boolean(data?.is_cold_start),
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
