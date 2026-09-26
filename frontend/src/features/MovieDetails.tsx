import { useParams } from "@tanstack/react-router";
import { ContentDetails } from "./ContentDetails";

export function MovieDetails() {
  const { id } = useParams({ from: "/movie/$id" });
  return <ContentDetails contentType="movie" id={Number(id)} />;
}
