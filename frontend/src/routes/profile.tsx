import { createFileRoute } from "@tanstack/react-router";
import { ProfilePage } from "@/features/UserPages";

export const Route = createFileRoute("/profile")({
  component: ProfilePage,
});
