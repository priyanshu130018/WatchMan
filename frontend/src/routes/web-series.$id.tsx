import { createFileRoute, useParams } from "@tanstack/react-router";
import { ContentDetails } from "@/features/ContentDetails";

export const Route = createFileRoute("/web-series/$id")({
  component: WebSeriesDetailsRouteComponent,
});

function WebSeriesDetailsRouteComponent() {
  const { id } = useParams({ from: "/web-series/$id" });
  return <ContentDetails contentType="tv" id={Number(id)} />;
}
