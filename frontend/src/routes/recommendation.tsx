import { createFileRoute } from "@tanstack/react-router";
import { RecommendationPage } from "@/features/RecommendationPage";

export const Route = createFileRoute("/recommendation")({
  component: RecommendationPage,
});
