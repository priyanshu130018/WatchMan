import { createFileRoute } from "@tanstack/react-router";
import { WatchHistoryPage } from "@/features/UserPages";

export const Route = createFileRoute("/history")({
  component: WatchHistoryPage,
});
