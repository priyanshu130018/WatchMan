export interface User {
  id: string | number;
  username: string;
  email: string;
  avatar_url?: string;
  favorite_genres?: string[];
  favorite_languages?: string[];
  stats?: {
    favorites: number;
    watched: number;
    recommendations: number;
  };
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  user: User;
}

export interface LoginPayload {
  email: string;
  password: string;
  remember?: boolean;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  favorite_genres?: string[];
  favorite_languages?: string[];
}
