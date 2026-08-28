export interface Genre {
  id: number;
  name: string;
}

export interface StreamingPlatform {
  id: number | string;
  name: string;
  logo_url?: string;
}

export interface CastMember {
  id: number;
  name: string;
  character?: string;
  profile_url?: string;
}

export interface Movie {
  id: number | string;
  title: string;
  original_title?: string;
  tagline?: string;
  overview?: string;
  poster_url?: string;
  backdrop_url?: string;
  release_date?: string;
  release_year?: number;
  runtime?: number;
  genres?: Genre[];
  languages?: string[];
  country?: string;
  director?: string;
  writer?: string;
  cast?: CastMember[];
  streaming_platforms?: StreamingPlatform[];
  imdb_rating?: number;
  tmdb_rating?: number;
  rabbit_match?: number;
  trailer_url?: string;
  is_favorite?: boolean;
}

export interface MovieSection {
  key: string;
  title: string;
  movies: Movie[];
}

export interface HomeResponse {
  featured?: Movie[];
  recommendations?: Movie[];
  trending?: Movie[];
  latest?: Movie[];
  netflix?: Movie[];
  prime?: Movie[];
  disney?: Movie[];
  hotstar?: Movie[];
  top_rated?: Movie[];
}

export interface Paginated<T> {
  results: T[];
  page: number;
  total_pages: number;
  total_results: number;
}

export interface SearchFilters {
  q?: string;
  genre?: string;
  language?: string;
  platform?: string;
  year?: string;
  sort?: "popularity" | "latest" | "imdb" | "rabbit";
  page?: number;
}
