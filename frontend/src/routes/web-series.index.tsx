import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { ContentListingPage } from "@/components/ContentListingPage";

const tvSearchSchema = z.object({
  page: z.number().optional(),
  genre: z.number().optional(),
  year: z.number().optional(),
  language: z.string().optional(),
  sort: z.string().optional(),
  collection: z.string().optional(),
});

export const Route = createFileRoute("/web-series/")({
  validateSearch: (search) => tvSearchSchema.parse(search),
  component: WebSeriesRouteComponent,
});

function WebSeriesRouteComponent() {
  const search = Route.useSearch();
  const navigate = useNavigate();

  return (
    <ContentListingPage
      title="Web Series"
      subtitle="TV Shows & Dramas"
      contentType="tv"
      searchParams={search}
      onUpdateFilters={(newFilters) => {
        void navigate({
          to: "/web-series",
          search: newFilters as any,
        });
      }}
    />
  );
}
