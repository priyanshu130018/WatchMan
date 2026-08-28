import { createFileRoute } from "@tanstack/react-router";
import { MovieDetailsPage } from "@/features/movie/MovieDetailsPage";

export const Route = createFileRoute("/movie/$id")({
  component: MovieDetailsPage,
});
