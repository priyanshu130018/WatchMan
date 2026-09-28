import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { ContentListingPage } from "@/components/ContentListingPage";

const movieSearchSchema = z.object({
  page: z.number().optional(),
  genre: z.number().optional(),
  year: z.number().optional(),
  language: z.string().optional(),
  sort: z.string().optional(),
  collection: z.string().optional(),
});

export const Route = createFileRoute("/movie/")({
  validateSearch: (search) => movieSearchSchema.parse(search),
  component: MoviesRouteComponent,
});

function MoviesRouteComponent() {
  const search = Route.useSearch();
  const navigate = useNavigate();

  return (
    <ContentListingPage
      title="Movies"
      subtitle="Film Discovery"
      contentType="movie"
      searchParams={search}
      onUpdateFilters={(newFilters) => {
        void navigate({
          to: "/movie",
          search: newFilters as any,
        });
      }}
    />
  );
}
