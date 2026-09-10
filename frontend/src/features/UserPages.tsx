import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';

import { MovieCard } from '@/components/MovieCard';
import { moviesService } from '@/services/movies';
import { userService } from '@/services/user';
import { useAuthStore } from '@/store/authStore';

type LibraryEntry = { movie_id: number };

function Guard({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((state) => state.user);
  if (!user) {
    return (
      <div className="page content-page">
        <h1>Sign in required</h1>
        <Link to="/login" className="primary">Sign in</Link>
      </div>
    );
  }
  return <>{children}</>;
}

function Library({ title, queryKey, loadEntries }: {
  title: string;
  queryKey: string;
  loadEntries: () => Promise<LibraryEntry[]>;
}) {
  const entries = useQuery({ queryKey: [queryKey], queryFn: loadEntries, refetchInterval: 30_000 });
  const movies = useQuery({
    queryKey: [queryKey, 'movies', entries.data?.map((entry) => entry.movie_id)],
    queryFn: () => Promise.all((entries.data ?? []).map((entry) => moviesService.detail(entry.movie_id))),
    enabled: Boolean(entries.data),
  });

  return (
    <div className="page content-page">
      <span className="eyebrow">YOUR LIBRARY</span>
      <h1>{title}</h1>
      <p className="muted">Saved and watched titles from your WatchMan account.</p>
      {entries.isLoading || movies.isLoading ? <p className="muted">Loading…</p> : null}
      {movies.data?.length ? (
        <div className="grid">{movies.data.map((movie) => <MovieCard key={movie.id} movie={movie} />)}</div>
      ) : !entries.isLoading ? <div className="empty">Nothing here yet. Start exploring.</div> : null}
    </div>
  );
}

export function Favorites() {
  return <Guard><Library title="Your favorites" queryKey="favorites" loadEntries={userService.favorites} /></Guard>;
}

export function History() {
  return <Guard><Library title="Watch history" queryKey="history" loadEntries={userService.history} /></Guard>;
}

export function Profile() {
  const user = useAuthStore((state) => state.user);
  return (
    <div className="page content-page">
      <span className="eyebrow">ACCOUNT</span>
      <h1>Your profile</h1>
      <div className="profile-card">
        <div className="avatar large">{user?.email?.[0]?.toUpperCase()}</div>
        <div>
          <h2>{user?.full_name || user?.email}</h2>
          <p className="muted">{user?.email}</p>
        </div>
      </div>
    </div>
  );
}
