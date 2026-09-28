import { api } from "@/lib/api";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";
import {
  type ContentItem,
  type ContentPagination,
  type ContentType,
  normalizeContentItem,
} from "@/types/content";

export interface OttProvider {
  provider_id: number;
  provider_name: string;
  logo_path?: string;
  display_priority?: number;
}

export interface OttRegion {
  iso_3166_1: string;
  english_name: string;
  native_name?: string;
}

export interface WatchProviderOffers {
  region: string;
  link?: string | null;
  flatrate: OttProvider[];
  rent: OttProvider[];
  buy: OttProvider[];
  free: OttProvider[];
  ads: OttProvider[];
}

export interface OttDiscoverParams {
  contentType: ContentType;
  providerId: number;
  region?: string;
  page?: number;
  sortBy?: string;
}

// Curated fallback used only if the live TMDB region list is unavailable. These
// are all real TMDB watch regions (ISO-3166-1), never fabricated availability.
export const FALLBACK_OTT_REGIONS: OttRegion[] = [
  { iso_3166_1: "IN", english_name: "India" },
  { iso_3166_1: "US", english_name: "United States" },
  { iso_3166_1: "GB", english_name: "United Kingdom" },
  { iso_3166_1: "CA", english_name: "Canada" },
  { iso_3166_1: "AU", english_name: "Australia" },
];

const emptyOffers = (region: string): WatchProviderOffers => ({
  region,
  link: null,
  flatrate: [],
  rent: [],
  buy: [],
  free: [],
  ads: [],
});

export const ottService = {
  getRegions: async (): Promise<OttRegion[]> => {
    const { data } = await api.get("/ott/regions");
    const results = Array.isArray(data?.results) ? (data.results as OttRegion[]) : [];
    return results.length > 0 ? results : FALLBACK_OTT_REGIONS;
  },

  getProviders: async (
    region = "IN",
    contentType: ContentType = "movie",
  ): Promise<OttProvider[]> => {
    const { data } = await api.get("/ott/providers", {
      params: { region, content_type: contentType },
    });
    return Array.isArray(data?.results) ? (data.results as OttProvider[]) : [];
  },

  discoverByProvider: async (params: OttDiscoverParams): Promise<ContentPagination> => {
    const { data } = await api.get(`/ott/${params.contentType}`, {
      params: {
        provider_id: params.providerId,
        region: params.region ?? "IN",
        page: params.page ?? 1,
        sort_by: params.sortBy,
      },
    });
    const results: ContentItem[] = Array.isArray(data?.results)
      ? data.results.map((r: unknown) => normalizeContentItem(r, params.contentType))
      : [];
    return {
      page: Number(data?.page ?? 1),
      limit: Number(data?.page_size ?? CONTENT_PAGE_SIZE),
      total: Number(data?.total_results ?? results.length),
      total_pages: Number(data?.total_pages ?? 1),
      results,
    };
  },

  getWatchProviders: async (
    contentType: ContentType,
    tmdbId: number,
    region = "IN",
  ): Promise<WatchProviderOffers> => {
    const path = contentType === "tv" ? "web-series" : "movies";
    const { data } = await api.get(`/${path}/${tmdbId}/watch-providers`, {
      params: { region },
    });
    if (!data || typeof data !== "object") return emptyOffers(region);
    return {
      region: data.region ?? region,
      link: data.link ?? null,
      flatrate: Array.isArray(data.flatrate) ? data.flatrate : [],
      rent: Array.isArray(data.rent) ? data.rent : [],
      buy: Array.isArray(data.buy) ? data.buy : [],
      free: Array.isArray(data.free) ? data.free : [],
      ads: Array.isArray(data.ads) ? data.ads : [],
    };
  },
};
