import { createFileRoute } from "@tanstack/react-router";
import { ForgotPassword } from "@/features/PasswordReset";

export const Route = createFileRoute("/forgot-password")({
  component: ForgotPassword,
});
