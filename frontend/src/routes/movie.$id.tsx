import { createFileRoute } from '@tanstack/react-router';

import { MovieDetails } from '@/features/MovieDetails';

export const Route = createFileRoute('/movie/$id')({
  component: MovieDetails,
});
