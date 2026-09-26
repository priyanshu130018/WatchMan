import {
  type ContentItem,
  type Genre,
  type CastMember,
  type CrewMember,
  imageUrl,
  normalizeContentItem,
} from "./content";

export type Movie = ContentItem;

export type RecommendationMovie = ContentItem & {
  recommendation_score: number;
  content_score: number;
  collaborative_score: number;
  popularity_score: number;
  reason: string;
  sources: string[];
};

export { imageUrl };

export function normalizeMovie(raw: any): Movie {
  return normalizeContentItem(raw, "movie");
}
