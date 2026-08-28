import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { authService } from "@/services/auth";
import { apiErrorMessage } from "@/api/client";
import { useAuthStore } from "@/store/authStore";
import { RabbitLogo } from "@/components/navbar/RabbitLogo";
import { Button } from "@/components/ui/button";

export function LoginPage() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  const mutation = useMutation({
    mutationFn: authService.login,
    onSuccess: (res) => {
      setAuth(res.access_token, res.user);
      toast.success(`Welcome back, ${res.user.username}`);
      navigate({ to: "/" });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Login failed")),
  });

  return (
    <AuthShell title="Welcome back">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ email, password, remember });
        }}
      >
        <Field
          label="Email"
          type="email"
          required
          value={email}
          onChange={setEmail}
        />
        <Field
          label="Password"
          type="password"
          required
          value={password}
          onChange={setPassword}
        />
        <div className="flex items-center justify-between text-sm">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="accent-[var(--rabbit-red)]"
            />
            Remember me
          </label>
          <a href="#" className="text-muted-foreground hover:text-foreground">
            Forgot password?
          </a>
        </div>
        <Button
          type="submit"
          disabled={mutation.isPending}
          className="w-full gradient-rabbit border-0"
        >
          {mutation.isPending ? "Signing in..." : "Sign In"}
        </Button>

        <div className="relative py-2 text-center text-xs text-muted-foreground">
          <span className="relative z-10 bg-card px-2">OR</span>
          <span className="absolute inset-x-0 top-1/2 h-px bg-white/10" />
        </div>

        <a href={authService.googleUrl()} className="block">
          <Button variant="secondary" type="button" className="w-full">
            Continue with Google
          </Button>
        </a>

        <p className="pt-2 text-center text-sm text-muted-foreground">
          Don't have an account?{" "}
          <Link to="/signup" className="text-primary hover:underline">
            Sign up
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}

export function AuthShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md items-center px-4">
      <div className="w-full rounded-3xl bg-card p-8 ring-1 ring-white/10 shadow-cinema">
        <div className="mb-6 flex items-center gap-3">
          <RabbitLogo className="h-10 w-10" />
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              Rabbit
            </p>
            <h1 className="text-xl font-bold">{title}</h1>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({
  label,
  type = "text",
  value,
  onChange,
  required,
  placeholder,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-widest text-muted-foreground">
        {label}
      </span>
      <input
        type={type}
        required={required}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/60"
      />
    </label>
  );
}
