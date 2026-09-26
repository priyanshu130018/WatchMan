export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  username?: string | null;
  avatar_url?: string | null;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  refresh_token?: string | null;
  user?: User | null;
}

export interface GenreSummary {
  id: number;
  tmdb_id: number;
  name: string;
}

export interface UserPreferences {
  user_id: string;
  favorite_genres: number[];
  disliked_genres: number[];
  favorite_genre_details: GenreSummary[];
  disliked_genre_details: GenreSummary[];
}

export interface ContentCardItem {
  id: number;
  tmdb_id: number;
  content_type: string;
  title: string;
  original_title?: string | null;
  overview?: string | null;
  release_date?: string | null;
  poster_path?: string | null;
  backdrop_path?: string | null;
  vote_average: number;
  vote_count: number;
  popularity: number;
  runtime?: number | null;
  number_of_seasons?: number | null;
  number_of_episodes?: number | null;
  genres: { id: number; name: string }[];
}

export interface SavedItem {
  id: number;
  user_id: string;
  content_id: number;
  movie_id: number;
  created_at: string;
  content?: ContentCardItem | null;
}

export interface RatingItem {
  id: number;
  user_id: string;
  content_id: number;
  movie_id: number;
  rating: number;
  review?: string | null;
  created_at: string;
  updated_at: string;
  content?: ContentCardItem | null;
}

export interface ReviewAuthor {
  id: string;
  username?: string | null;
  full_name?: string | null;
  avatar_url?: string | null;
}

export interface ReviewItem {
  id: number;
  user_id: string;
  content_id: number;
  title?: string | null;
  content: string;
  rating?: number | null;
  status: string;
  created_at: string;
  updated_at: string;
  author?: ReviewAuthor | null;
  content_item?: ContentCardItem | null;
}

export interface WatchHistoryItem {
  id: number;
  user_id: string;
  content_id: number;
  movie_id: number;
  progress: number;
  completed: boolean;
  watched_at: string;
  content?: ContentCardItem | null;
}
