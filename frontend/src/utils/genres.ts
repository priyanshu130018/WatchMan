export const GENRE_OPTIONS = [
  "Action",
  "Adventure",
  "Animation",
  "Comedy",
  "Crime",
  "Documentary",
  "Drama",
  "Family",
  "Fantasy",
  "Horror",
  "Mystery",
  "Romance",
  "Sci-Fi",
  "Thriller",
  "War",
  "Western",
];

export const LANGUAGE_OPTIONS = [
  "English",
  "Hindi",
  "Spanish",
  "French",
  "Korean",
  "Japanese",
  "German",
  "Italian",
  "Tamil",
  "Telugu",
];

export const PLATFORM_OPTIONS = [
  "Netflix",
  "Prime Video",
  "Disney+",
  "JioHotstar",
  "Apple TV+",
  "HBO Max",
];

export const YEAR_OPTIONS = Array.from({ length: 30 }, (_, i) =>
  String(2026 - i),
);
