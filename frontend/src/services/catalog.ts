import { api } from "@/lib/api";
import {
  type ContentItem,
  type ContentPagination,
  type ContentType,
  normalizeContentItem,
} from "@/types/content";

export interface CatalogFilterParams {
  page?: number;
  limit?: number;
  sort?: string;
  year?: number;
  genre_id?: number;
  language?: string;
}

export interface SearchFilterParams extends CatalogFilterParams {
  q: string;
  type?: "all" | "movie" | "tv";
}

export interface TrendingParams {
  type?: "all" | "movie" | "tv";
  timeWindow?: "day" | "week";
  page?: number;
}

export interface TmdbImage {
  file_path: string;
  width?: number;
  height?: number;
  aspect_ratio?: number;
  vote_average?: number;
}

export interface ImagesResponse {
  backdrops: TmdbImage[];
  posters: TmdbImage[];
}

export interface TmdbReview {
  id: string;
  author: string;
  rating?: number | null;
  avatar_path?: string | null;
  content: string;
  created_at?: string;
  url?: string;
}

export interface TmdbReviewsResponse {
  page: number;
  total_pages: number;
  total_results: number;
  results: TmdbReview[];
}

export const MOVIE_GENRES = [
  { id: 28, name: "Action" },
  { id: 12, name: "Adventure" },
  { id: 16, name: "Animation" },
  { id: 35, name: "Comedy" },
  { id: 80, name: "Crime" },
  { id: 99, name: "Documentary" },
  { id: 18, name: "Drama" },
  { id: 10751, name: "Family" },
  { id: 14, name: "Fantasy" },
  { id: 36, name: "History" },
  { id: 27, name: "Horror" },
  { id: 10402, name: "Music" },
  { id: 9648, name: "Mystery" },
  { id: 10749, name: "Romance" },
  { id: 878, name: "Sci-Fi" },
  { id: 10770, name: "TV Movie" },
  { id: 53, name: "Thriller" },
  { id: 10752, name: "War" },
  { id: 37, name: "Western" },
];

export const TV_GENRES = [
  { id: 10759, name: "Action & Adventure" },
  { id: 16, name: "Animation" },
  { id: 35, name: "Comedy" },
  { id: 80, name: "Crime" },
  { id: 99, name: "Documentary" },
  { id: 18, name: "Drama" },
  { id: 10751, name: "Family" },
  { id: 10762, name: "Kids" },
  { id: 9648, name: "Mystery" },
  { id: 10763, name: "News" },
  { id: 10764, name: "Reality" },
  { id: 10765, name: "Sci-Fi & Fantasy" },
  { id: 10766, name: "Soap" },
  { id: 10767, name: "Talk" },
  { id: 10768, name: "War & Politics" },
  { id: 37, name: "Western" },
];

// ISO 639-1 language codes matching TMDB's `original_language` field.
export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "hi", name: "Hindi" },
  { code: "es", name: "Spanish" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
  { code: "it", name: "Italian" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "zh", name: "Chinese" },
  { code: "ta", name: "Tamil" },
  { code: "te", name: "Telugu" },
  { code: "pt", name: "Portuguese" },
  { code: "ru", name: "Russian" },
  { code: "ar", name: "Arabic" },
  { code: "tr", name: "Turkish" },
];

export const catalogService = {
  getMovies: async (params?: CatalogFilterParams): Promise<ContentPagination> => {
    const { data } = await api.get("/movies", {
      params: {
        page: params?.page ?? 1,
        limit: params?.limit ?? 16,
        sort: params?.sort ?? "popularity_desc",
        year: params?.year,
        genre_id: params?.genre_id,
        language: params?.language,
      },
    });

    const results = Array.isArray(data?.results)
      ? data.results.map((r: any) => normalizeContentItem(r, "movie"))
      : [];
    return {
      page: Number(data?.page ?? 1),
      limit: Number(data?.limit ?? 16),
      total: Number(data?.total ?? results.length),
      total_pages: Number(data?.total_pages ?? 1),
      results,
    };
  },

  getMovieDetail: async (id: number): Promise<ContentItem> => {
    const { data } = await api.get(`/movies/${id}`);
    return normalizeContentItem(data, "movie");
  },

  getMovieSimilar: async (id: number): Promise<ContentItem[]> => {
    const { data } = await api.get(`/movies/${id}/similar`);
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((item: unknown) =>
      normalizeContentItem((item as { movie?: unknown }).movie ?? item, "movie"),
    );
  },

  getTrendingMovies: async (timeWindow: "day" | "week" = "week"): Promise<ContentItem[]> => {
    const { data } = await api.get("/movies/trending", { params: { time_window: timeWindow } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "movie"));
  },

  getPopularMovies: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/movies/popular", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "movie"));
  },

  getTopRatedMovies: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/movies/top-rated", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "movie"));
  },

  getLatestMovies: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/movies/latest", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "movie"));
  },

  getWebSeries: async (params?: CatalogFilterParams): Promise<ContentPagination> => {
    const { data } = await api.get("/web-series", {
      params: {
        page: params?.page ?? 1,
        limit: params?.limit ?? 16,
        sort: params?.sort ?? "popularity_desc",
        year: params?.year,
        genre_id: params?.genre_id,
        language: params?.language,
      },
    });

    const results = Array.isArray(data?.results)
      ? data.results.map((r: any) => normalizeContentItem(r, "tv"))
      : [];
    return {
      page: Number(data?.page ?? 1),
      limit: Number(data?.limit ?? 16),
      total: Number(data?.total ?? results.length),
      total_pages: Number(data?.total_pages ?? 1),
      results,
    };
  },

  getWebSeriesDetail: async (id: number): Promise<ContentItem> => {
    const { data } = await api.get(`/web-series/${id}`);
    return normalizeContentItem(data, "tv");
  },

  getWebSeriesSimilar: async (id: number): Promise<ContentItem[]> => {
    const { data } = await api.get(`/web-series/${id}/similar`);
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "tv"));
  },

  getTrendingWebSeries: async (timeWindow: "day" | "week" = "week"): Promise<ContentItem[]> => {
    const { data } = await api.get("/web-series/trending", { params: { time_window: timeWindow } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "tv"));
  },

  getPopularWebSeries: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/web-series/popular", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "tv"));
  },

  getTopRatedWebSeries: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/web-series/top-rated", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "tv"));
  },

  getLatestWebSeries: async (page = 1): Promise<ContentItem[]> => {
    const { data } = await api.get("/web-series/latest", { params: { page } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, "tv"));
  },

  getTrending: async (params?: TrendingParams): Promise<ContentItem[]> => {
    const { data } = await api.get("/trending", {
      params: {
        content_type: params?.type && params.type !== "all" ? params.type : undefined,
        time_window: params?.timeWindow ?? "week",
        page: params?.page ?? 1,
      },
    });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((r: any) => normalizeContentItem(r, params?.type === "tv" ? "tv" : "movie"));
  },

  search: async (params: SearchFilterParams): Promise<ContentPagination> => {
    const { data } = await api.get("/search", {
      params: {
        q: params.q,
        query: params.q,
        content_type: params.type && params.type !== "all" ? params.type : undefined,
        genre_id: params.genre_id,
        year: params.year,
        sort: params.sort,
        page: params.page ?? 1,
      },
    });

    const rawResults = Array.isArray(data?.results) ? data.results : [];
    const results = rawResults.map((r: any) => normalizeContentItem(r));
    return {
      page: Number(data?.page ?? 1),
      limit: Number(data?.limit ?? 16),
      total: Number(data?.total ?? results.length),
      total_pages: Number(
        data?.total_pages ?? Math.max(1, Math.ceil((data?.total ?? results.length) / 16)),
      ),
      results,
    };
  },

  getImages: async (contentType: ContentType, id: number): Promise<ImagesResponse> => {
    const path = contentType === "tv" ? "web-series" : "movies";
    const { data } = await api.get(`/${path}/${id}/images`);
    return {
      backdrops: Array.isArray(data?.backdrops) ? data.backdrops : [],
      posters: Array.isArray(data?.posters) ? data.posters : [],
    };
  },

  getTmdbReviews: async (
    contentType: ContentType,
    id: number,
    page = 1,
  ): Promise<TmdbReviewsResponse> => {
    const path = contentType === "tv" ? "web-series" : "movies";
    const { data } = await api.get(`/${path}/${id}/tmdb-reviews`, { params: { page } });
    return {
      page: Number(data?.page ?? 1),
      total_pages: Number(data?.total_pages ?? 1),
      total_results: Number(data?.total_results ?? 0),
      results: Array.isArray(data?.results) ? data.results : [],
    };
  },
};
