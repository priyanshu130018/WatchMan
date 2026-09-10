import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from '@tanstack/react-router';
import { ArrowLeft, Heart, Play, Star, Clock } from 'lucide-react';

import { MovieCard } from '@/components/MovieCard';
import { moviesService } from '@/services/movies';
import { userService } from '@/services/user';
import { useAuthStore } from '@/store/authStore';
import { rating, runtime, year } from '@/utils/format';

export function MovieDetails() {
  const { id } = useParams({ from: '/movie/$id' });
  const movieId = Number(id);
  const token = useAuthStore((state) => state.token);
  const queryClient = useQueryClient();
  const movie = useQuery({
    queryKey: ['movies', movieId],
    queryFn: () => moviesService.detail(movieId),
    refetchInterval: 60_000,
  });
  const similar = useQuery({
    queryKey: ['movies', 'similar', movieId],
    queryFn: () => moviesService.similar(movieId),
    enabled: movie.isSuccess,
    refetchInterval: 60_000,
  });
  const favorites = useQuery({ queryKey: ['favorites'], queryFn: userService.favorites, enabled: Boolean(token) });
  const ratings = useQuery({ queryKey: ['ratings'], queryFn: userService.ratings, enabled: Boolean(token) });
  const isFavorite = favorites.data?.some((favorite) => favorite.movie_id === movieId) ?? false;
  const currentRating = ratings.data?.find((entry) => entry.movie_id === movieId)?.rating;
  const favoriteMutation = useMutation({
    mutationFn: () => isFavorite ? userService.removeFavorite(movieId) : userService.addFavorite(movieId),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['favorites'] }),
      queryClient.invalidateQueries({ queryKey: ['recommendations', 'personalized'] }),
    ]),
  });
  const ratingMutation = useMutation({
    mutationFn: (value: number) => userService.rateMovie(movieId, value),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['ratings'] }),
      queryClient.invalidateQueries({ queryKey: ['recommendations', 'personalized'] }),
    ]),
  });

  if (movie.isLoading) return <div className="page"><div className="loading-block" /></div>;
  if (!movie.data) return <div className="page"><p>Movie not found.</p></div>;

  const currentMovie = movie.data;
  return (
    <div>
      <section className="detail-hero">
        {currentMovie.backdrop_url ? <img src={currentMovie.backdrop_url} alt="" /> : null}
        <div className="hero-overlay" />
        <div className="detail-content page">
          <Link to="/" className="back"><ArrowLeft size={15} /> Back</Link>
          <div className="detail-grid">
            {currentMovie.poster_url ? <img className="detail-poster" src={currentMovie.poster_url} alt={currentMovie.title} /> : null}
            <div>
              <span className="eyebrow">MOVIE</span>
              <h1>{currentMovie.title}</h1>
              {currentMovie.tagline ? <p className="tagline">{currentMovie.tagline}</p> : null}
              <div className="facts">
                <span>{year(currentMovie.release_date)}</span>
                {currentMovie.runtime ? <span><Clock size={14} />{runtime(currentMovie.runtime)}</span> : null}
                {currentMovie.vote_average != null ? <span><Star size={14} fill="currentColor" />{rating(currentMovie.vote_average)}</span> : null}
              </div>
              <p className="overview">{currentMovie.overview}</p>
              <div className="actions-row">
                {currentMovie.trailer_url ? <a className="primary" href={currentMovie.trailer_url} target="_blank" rel="noreferrer"><Play size={16} fill="currentColor" />Trailer</a> : null}
                {token ? <button type="button" className="secondary" onClick={() => favoriteMutation.mutate()}><Heart size={16} fill={isFavorite ? 'currentColor' : 'none'} />{isFavorite ? 'Saved' : 'Save'}</button> : null}
              </div>
              {token ? (
                <div className="rating-control" aria-label="Rate this movie">
                  <span>Your rating:</span>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button type="button" key={value} onClick={() => ratingMutation.mutate(value)} className={currentRating && value <= currentRating ? 'active' : ''}>
                      <Star size={16} fill={currentRating && value <= currentRating ? 'currentColor' : 'none'} />
                    </button>
                  ))}
                </div>
              ) : null}
              <div className="chips">{currentMovie.genres?.map((genre) => <span key={genre.id ?? genre.name}>{genre.name}</span>)}</div>
            </div>
          </div>
        </div>
      </section>
      <div className="page">
        <section className="section">
          <div className="section-head"><div><span className="eyebrow">KEEP WATCHING</span><h2>More like this</h2></div></div>
          <div className="grid">{similar.data?.map((item) => <MovieCard key={item.id} movie={item} />)}</div>
        </section>
      </div>
    </div>
  );
}
