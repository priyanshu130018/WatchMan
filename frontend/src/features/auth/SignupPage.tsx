import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { authService } from "@/services/auth";
import { apiErrorMessage } from "@/api/client";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/ui/button";
import { GENRE_OPTIONS, LANGUAGE_OPTIONS } from "@/utils/genres";
import { AuthShell, Field } from "./LoginPage";

export function SignupPage() {
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [genres, setGenres] = useState<string[]>([]);
  const [langs, setLangs] = useState<string[]>([]);

  const toggle = (
    v: string,
    set: React.Dispatch<React.SetStateAction<string[]>>,
  ) => set((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]));

  const mutation = useMutation({
    mutationFn: authService.register,
    onSuccess: (res) => {
      setAuth(res.access_token, res.user);
      toast.success("Welcome to Rabbit!");
      navigate({ to: "/" });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Signup failed")),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error("Passwords do not match");
      return;
    }
    mutation.mutate({
      username,
      email,
      password,
      favorite_genres: genres,
      favorite_languages: langs,
    });
  };

  return (
    <AuthShell title="Create your account">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Username" required value={username} onChange={setUsername} />
        <Field label="Email" type="email" required value={email} onChange={setEmail} />
        <Field label="Password" type="password" required value={password} onChange={setPassword} />
        <Field
          label="Confirm Password"
          type="password"
          required
          value={confirm}
          onChange={setConfirm}
        />

        <div>
          <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">
            Favorite Genres
          </p>
          <div className="flex flex-wrap gap-2">
            {GENRE_OPTIONS.slice(0, 10).map((g) => (
              <Chip
                key={g}
                active={genres.includes(g)}
                onClick={() => toggle(g, setGenres)}
              >
                {g}
              </Chip>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">
            Favorite Languages
          </p>
          <div className="flex flex-wrap gap-2">
            {LANGUAGE_OPTIONS.slice(0, 8).map((l) => (
              <Chip
                key={l}
                active={langs.includes(l)}
                onClick={() => toggle(l, setLangs)}
              >
                {l}
              </Chip>
            ))}
          </div>
        </div>

        <Button
          type="submit"
          disabled={mutation.isPending}
          className="w-full gradient-rabbit border-0"
        >
          {mutation.isPending ? "Creating..." : "Register"}
        </Button>

        <p className="pt-2 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition ${
        active
          ? "border-primary bg-primary/20"
          : "border-white/10 bg-white/5 text-muted-foreground hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}
