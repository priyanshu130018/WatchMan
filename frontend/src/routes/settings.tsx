import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/features/UserPages";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
});
