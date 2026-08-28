import { createFileRoute } from "@tanstack/react-router";
import { FavoritesPage } from "@/features/favorites/FavoritesPage";

export const Route = createFileRoute("/favorites")({
  component: FavoritesPage,
});
