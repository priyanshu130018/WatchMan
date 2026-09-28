import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { ContentListingPage } from "@/components/ContentListingPage";

const movieSearchSchema = z.object({
  page: z.coerce.number().optional(),
  genre: z.coerce.number().optional(),
  genre_id: z.coerce.number().optional(),
  year: z.coerce.number().optional(),
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
          search: () => (newFilters || {}) as any,
        });
      }}
    />
  );
}
