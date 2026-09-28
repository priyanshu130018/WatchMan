import { useState } from "react";
import { useNavigate, Link } from "@tanstack/react-router";
import { authService, isSupabaseAuth } from "@/services/auth";
import { useAuthStore } from "@/store/authStore";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function Auth({ mode }: { mode: "login" | "signup" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nav = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const resp =
        mode === "login"
          ? await authService.login(email.trim(), password)
          : await authService.register(
              email.trim(),
              password,
              name.trim() || undefined,
              username.trim() || undefined,
            );

      // Supabase signup with email confirmation returns no session yet — there
      // is nothing to authenticate against, so guide the user to verify first.
      if (!resp.access_token) {
        toast.success("Account created. Check your email to confirm your address, then sign in.");
        nav({ to: "/login" });
        return;
      }

      const currentUser = resp.user || (await authService.me());
      setSession(resp.access_token, currentUser, resp.refresh_token);
      toast.success(mode === "login" ? "Signed in." : "Welcome to WatchMan!");
      nav({ to: "/" });
    } catch (err: unknown) {
      const message = getApiErrorMessage(err);
      setError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mb-3 flex flex-col items-center gap-2">
            <img
              src="/watchman-icon.png"
              alt=""
              className="h-20 w-20 rounded-2xl object-cover"
              width={80}
              height={80}
            />
            <span className="text-lg font-bold tracking-tight">WatchMan</span>
          </div>
          <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
            {mode === "login" ? "Welcome back" : "Join WatchMan"}
          </span>
          <CardTitle className="text-2xl">
            {mode === "login" ? "Sign in" : "Create your account"}
          </CardTitle>
          <CardDescription>
            {mode === "login"
              ? "Continue discovering movies and series you will actually finish."
              : "Build your profile and let your taste shape personalized discovery."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form
            onSubmit={submit}
            aria-label={mode === "login" ? "Sign in form" : "Sign up form"}
            className="space-y-4"
          >
            {mode === "signup" && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="name-input">Full name</Label>
                  <Input
                    id="name-input"
                    type="text"
                    placeholder="e.g. Priyanshu Sharma"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={isSubmitting}
                    autoComplete="name"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="username-input">Username</Label>
                  <Input
                    id="username-input"
                    type="text"
                    placeholder="e.g. priyanshu13"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={isSubmitting}
                    autoComplete="username"
                  />
                </div>
              </>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="email-input">Email address</Label>
              <Input
                id="email-input"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
                autoComplete="email"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password-input">Password</Label>
              <Input
                id="password-input"
                type="password"
                placeholder="At least 8 characters"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
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
              {isSubmitting
                ? mode === "login"
                  ? "Signing in…"
                  : "Creating account…"
                : mode === "login"
                  ? "Sign in"
                  : "Create account"}
            </Button>
          </form>

          {mode === "login" && isSupabaseAuth && (
            <p className="mt-4 text-center text-sm">
              <Link to="/forgot-password" className="font-medium text-primary hover:underline">
                Forgot your password?
              </Link>
            </p>
          )}

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {mode === "login" ? (
              <>
                New to WatchMan?{" "}
                <Link to="/signup" className="font-medium text-primary hover:underline">
                  Create an account
                </Link>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <Link to="/login" className="font-medium text-primary hover:underline">
                  Sign in
                </Link>
              </>
            )}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
