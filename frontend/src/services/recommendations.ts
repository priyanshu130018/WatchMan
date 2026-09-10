import { api } from '@/lib/api';
import { normalizeMovie, type RecommendationMovie } from '@/types/movie';

export const recommendationService = {
  personalized: async (limit = 20): Promise<RecommendationMovie[]> => {
    const { data } = await api.get('/recommendations/personalized', { params: { limit } });
    const results = Array.isArray(data?.results) ? data.results : [];
    return results.map((item: unknown) => normalizeMovie(item) as RecommendationMovie);
  },
};
