import { useQueries, useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Play, Search, Sparkles } from 'lucide-react';

import { MovieRow } from '@/components/MovieRow';
import { recommendationService } from '@/services/recommendations';
import { moviesService } from '@/services/movies';
import { useAuthStore } from '@/store/authStore';

const LIVE_REFRESH_MS = 30_000;

export function Home() {
  const token = useAuthStore((state) => state.token);
  const [trendingQuery, popularQuery, topRatedQuery, latestQuery] = useQueries({
    queries: [
      { queryKey: ['movies', 'trending'], queryFn: moviesService.trending, refetchInterval: LIVE_REFRESH_MS },
      { queryKey: ['movies', 'popular'], queryFn: moviesService.popular, refetchInterval: LIVE_REFRESH_MS },
      { queryKey: ['movies', 'top-rated'], queryFn: moviesService.topRated, refetchInterval: LIVE_REFRESH_MS },
      { queryKey: ['movies', 'latest'], queryFn: moviesService.latest, refetchInterval: LIVE_REFRESH_MS },
    ],
  });
  const personalizedQuery = useQuery({
    queryKey: ['recommendations', 'personalized'],
    queryFn: () => recommendationService.personalized(16),
    enabled: Boolean(token),
    refetchInterval: LIVE_REFRESH_MS,
  });

  const trending = trendingQuery.data ?? [];
  const popular = popularQuery.data ?? [];
  const topRated = topRatedQuery.data ?? [];
  const latest = latestQuery.data ?? [];
  const hero = trending[0] ?? popular[0];

  return (
    <div>
      <section className="hero">
        {hero?.backdrop_url ? <img src={hero.backdrop_url} alt="" /> : null}
        <div className="hero-overlay" />
        <div className="hero-content">
          <div className="eyebrow">
            <Sparkles size={14} /> PERSONALIZED MOVIE DISCOVERY
          </div>
          <h1>
            Find your next
            <br />
            <em>great watch.</em>
          </h1>
          <p>Live catalog data, plus recommendations shaped by your favorites, viewing progress, and ratings.</p>
          <div className="hero-actions">
            <Link
              to={hero ? '/movie/$id' : '/search'}
              params={hero ? { id: String(hero.id) } : undefined}
              className="primary"
            >
              <Play size={17} fill="currentColor" />
              {hero ? 'Explore this movie' : 'Start exploring'}
            </Link>
            <Link to="/search" className="secondary">
              <Search size={17} /> Search the catalog
            </Link>
          </div>
        </div>
      </section>
      <div className="page">
        {personalizedQuery.data?.length ? (
          <MovieRow title="Picked for you" movies={personalizedQuery.data} />
        ) : null}
        <MovieRow title="Trending now" movies={trending} />
        <MovieRow title="Popular picks" movies={popular} />
        <MovieRow title="Top rated" movies={topRated} />
        <MovieRow title="Now playing" movies={latest} />
      </div>
    </div>
  );
}
