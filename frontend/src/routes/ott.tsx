import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";

import { OttPage } from "@/features/OttPage";

const ottSearchSchema = z.object({
  region: z.string().optional(),
  type: z.enum(["movie", "tv"]).optional(),
  provider: z.number().optional(),
  page: z.number().optional(),
});

export const Route = createFileRoute("/ott")({
  validateSearch: (search) => ottSearchSchema.parse(search),
  component: OttRouteComponent,
});

function OttRouteComponent() {
  const search = Route.useSearch();
  const navigate = useNavigate();

  return (
    <OttPage
      searchParams={search}
      onUpdateFilters={(newFilters) => {
        void navigate({
          to: "/ott",
          search: newFilters as any,
        });
      }}
    />
  );
}
