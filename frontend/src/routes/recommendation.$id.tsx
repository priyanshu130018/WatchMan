import { createFileRoute, useParams } from "@tanstack/react-router";
import { z } from "zod";
import { ContentDetails } from "@/features/ContentDetails";

const detailSearchSchema = z.object({
  type: z.enum(["movie", "tv"]).optional().default("movie"),
});

export const Route = createFileRoute("/recommendation/$id")({
  validateSearch: (search) => detailSearchSchema.parse(search),
  component: RecommendationDetailRouteComponent,
});

function RecommendationDetailRouteComponent() {
  const { id } = useParams({ from: "/recommendation/$id" });
  const { type } = Route.useSearch();
  return <ContentDetails contentType={type} id={Number(id)} />;
}
