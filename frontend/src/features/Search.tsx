import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { Search as SearchIcon } from 'lucide-react';

import { MovieCard } from '@/components/MovieCard';
import { moviesService } from '@/services/movies';

export function SearchPage() {
  const params = useSearch({ from: '/search' });
  const navigate = useNavigate({ from: '/search' });
  const [queryText, setQueryText] = useState(params.q ?? '');
  const query = useQuery({
    queryKey: ['movies', 'search', params.q],
    queryFn: () => moviesService.search(params.q ?? ''),
    enabled: Boolean(params.q),
    refetchInterval: 30_000,
  });

  return (
    <div className="page content-page">
      <div className="search-header">
        <span className="eyebrow">DISCOVER</span>
        <h1>Search the catalog</h1>
        <p>Searches update directly from the API and refresh while this page is open.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void navigate({ search: { q: queryText.trim() || undefined } });
          }}
          className="large-search"
        >
          <SearchIcon />
          <input
            value={queryText}
            onChange={(event) => setQueryText(event.target.value)}
            placeholder="Fight Club, Interstellar, Nolan..."
          />
          <button type="submit">Search</button>
        </form>
      </div>
      {query.isLoading ? <p className="muted">Searching…</p> : null}
      {query.data?.length === 0 ? <p className="empty">No movies found.</p> : null}
      <div className="grid">
        {query.data?.map((movie) => <MovieCard key={movie.id} movie={movie} />)}
      </div>
    </div>
  );
}
