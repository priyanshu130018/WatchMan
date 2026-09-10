import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Heart, Play, Star } from 'lucide-react';

import { useAuthStore } from '@/store/authStore';
import { type Movie } from '@/types/movie';
import { rating, year } from '@/utils/format';
import { userService } from '@/services/user';

export function MovieCard({ movie }: { movie: Movie }) {
  const token = useAuthStore((state) => state.token);
  const queryClient = useQueryClient();
  const favorites = useQuery({
    queryKey: ['favorites'],
    queryFn: userService.favorites,
    enabled: Boolean(token),
    refetchInterval: 30_000,
  });
  const isFavorite = favorites.data?.some((favorite) => favorite.movie_id === movie.id) ?? false;
  const favoriteMutation = useMutation({
    mutationFn: () =>
      isFavorite ? userService.removeFavorite(movie.id) : userService.addFavorite(movie.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['favorites'] });
      await queryClient.invalidateQueries({ queryKey: ['recommendations', 'personalized'] });
    },
  });

  return (
    <Link to="/movie/$id" params={{ id: String(movie.id) }} className="group block min-w-0">
      <article className="movie-card">
        <div className="poster">
          {movie.poster_url ? (
            <img src={movie.poster_url} alt={movie.title} loading="lazy" />
          ) : null}
          <div className="poster-shade" />
          {token ? (
            <button
              type="button"
              className={`fav ${isFavorite ? 'active' : ''}`}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                favoriteMutation.mutate();
              }}
              disabled={favoriteMutation.isPending}
              aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
            >
              <Heart size={17} fill={isFavorite ? 'currentColor' : 'none'} />
            </button>
          ) : null}
          <span className="quick">
            <Play size={14} fill="currentColor" /> Details
          </span>
        </div>
        <div className="pt-3">
          <h3>{movie.title}</h3>
          {movie.reason ? <p className="recommendation-reason">{movie.reason}</p> : null}
          <div className="meta">
            <span>{year(movie.release_date)}</span>
            {movie.vote_average != null ? (
              <>
                <span>•</span>
                <span>
                  <Star size={12} fill="currentColor" /> {rating(movie.vote_average)}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </article>
    </Link>
  );
}
