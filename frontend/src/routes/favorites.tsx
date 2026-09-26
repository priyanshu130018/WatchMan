import { createFileRoute } from "@tanstack/react-router";
import { SavedContentPage } from "@/features/UserPages";

export const Route = createFileRoute("/favorites")({
  component: SavedContentPage,
});
