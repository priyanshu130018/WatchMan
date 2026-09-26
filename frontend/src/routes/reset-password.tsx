import { createFileRoute } from "@tanstack/react-router";
import { ResetPassword } from "@/features/PasswordReset";

export const Route = createFileRoute("/reset-password")({
  component: ResetPassword,
});
