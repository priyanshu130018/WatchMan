import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { authService, isSupabaseAuth } from "@/services/auth";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function Shell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mb-2 flex items-center justify-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-gradient font-extrabold text-white">
              W
            </span>
            <span className="text-lg font-bold tracking-tight">WatchMan</span>
          </div>
          <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
            {eyebrow}
          </span>
          <CardTitle className="text-2xl">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  );
}

function Disabled({ title }: { title: string }) {
  return (
    <Shell
      eyebrow="Account recovery"
      title={title}
      description="Password recovery is handled by Supabase Auth and is not enabled for this deployment."
    >
      <p className="text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </Shell>
  );
}

/** Request a password-reset email (Supabase sends a recovery link → /reset-password). */
export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isSupabaseAuth) return <Disabled title="Reset your password" />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await authService.requestPasswordReset(email.trim());
      setSent(true);
      toast.success("Password-reset link sent. Check your inbox.");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Could not send reset email.";
      setError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Shell
      eyebrow="Account recovery"
      title="Reset your password"
      description="Enter your email and we'll send you a secure link to choose a new password."
    >
      {sent ? (
        <div className="space-y-4">
          <p
            role="status"
            aria-live="polite"
            className="rounded-lg border border-primary/30 bg-primary/10 px-3.5 py-2.5 text-sm"
          >
            If an account exists for <strong>{email}</strong>, a password-reset link is on its way.
            Check your inbox and spam folder.
          </p>
          <p className="text-center text-sm text-muted-foreground">
            <Link to="/login" className="font-medium text-primary hover:underline">
              Back to sign in
            </Link>
          </p>
        </div>
      ) : (
        <form onSubmit={submit} aria-label="Password reset request form" className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="reset-email">Email address</Label>
            <Input
              id="reset-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
              autoComplete="email"
            />
          </div>

          {error && (
            <p
              role="alert"
              aria-live="assertive"
              className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive"
            >
              {error}
            </p>
          )}

          <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Sending link…" : "Send reset link"}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            Remembered it?{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Back to sign in
            </Link>
          </p>
        </form>
      )}
    </Shell>
  );
}

/** Set a new password. Supabase establishes a recovery session when the user
 *  arrives via the emailed link, so updateUser({ password }) succeeds here. */
export function ResetPassword() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const nav = useNavigate();

  if (!isSupabaseAuth) return <Disabled title="Choose a new password" />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await authService.updatePassword(password);
      setDone(true);
      toast.success("Password updated. You can now sign in.");
      setTimeout(() => nav({ to: "/login" }), 1800);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Could not update password. Your reset link may have expired — request a new one.";
      setError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Shell
      eyebrow="Account recovery"
      title="Choose a new password"
      description="Enter and confirm a new password for your account."
    >
      {done ? (
        <div className="space-y-4">
          <p
            role="status"
            aria-live="polite"
            className="rounded-lg border border-primary/30 bg-primary/10 px-3.5 py-2.5 text-sm"
          >
            Your password has been updated. Redirecting you to sign in…
          </p>
          <p className="text-center text-sm text-muted-foreground">
            <Link to="/login" className="font-medium text-primary hover:underline">
              Sign in now
            </Link>
          </p>
        </div>
      ) : (
        <form onSubmit={submit} aria-label="Set new password form" className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              placeholder="At least 8 characters"
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isSubmitting}
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm-password">Confirm new password</Label>
            <Input
              id="confirm-password"
              type="password"
              placeholder="Re-enter your new password"
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              disabled={isSubmitting}
              autoComplete="new-password"
            />
          </div>

          {error && (
            <p
              role="alert"
              aria-live="assertive"
              className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive"
            >
              {error}
            </p>
          )}

          <Button type="submit" variant="brand" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Updating…" : "Update password"}
          </Button>
        </form>
      )}
    </Shell>
  );
}
