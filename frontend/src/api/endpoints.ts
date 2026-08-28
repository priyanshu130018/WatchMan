export const endpoints = {
  home: "/home",
  movie: (id: string | number) => `/movies/${id}`,
  search: "/search",
  profile: "/profile",
  favorites: "/favorites",
  favorite: (movieId: string | number) => `/favorites/${movieId}`,
  history: "/history",
  auth: {
    login: "/auth/login",
    register: "/auth/register",
    logout: "/auth/logout",
    google: "/auth/google",
    me: "/auth/me",
  },
} as const;
