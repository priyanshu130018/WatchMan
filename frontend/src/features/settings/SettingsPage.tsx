import { useEffect } from "react";
import { useUIStore, type Theme } from "@/store/uiStore";
import { useAuthStore } from "@/store/authStore";
import { authService } from "@/services/auth";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";

const THEMES: { key: Theme; label: string; icon: React.ReactNode }[] = [
  { key: "dark", label: "Dark", icon: <Moon className="h-4 w-4" /> },
  { key: "light", label: "Light", icon: <Sun className="h-4 w-4" /> },
  { key: "system", label: "System", icon: <Monitor className="h-4 w-4" /> },
];

export function SettingsPage() {
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme !== "light");
  }, [theme]);

  const logout = async () => {
    try {
      await authService.logout();
    } catch {
      /* ignore */
    }
    clear();
    navigate({ to: "/" });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-2xl font-black">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Personalize your Rabbit experience
        </p>
      </div>

      <Section title="Theme">
        <div className="grid grid-cols-3 gap-2">
          {THEMES.map((t) => (
            <button
              key={t.key}
              onClick={() => setTheme(t.key)}
              className={`flex items-center justify-center gap-2 rounded-xl border p-3 text-sm transition ${
                theme === t.key
                  ? "border-primary bg-primary/10"
                  : "border-white/10 bg-white/5 hover:bg-white/10"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Language">
        <select className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm">
          <option>English</option>
          <option>हिन्दी</option>
          <option>Español</option>
          <option>Français</option>
        </select>
      </Section>

      <Section title="Notifications">
        <Toggle label="Email digests" />
        <Toggle label="New AI recommendations" defaultChecked />
        <Toggle label="Product updates" />
      </Section>

      <Section title="Privacy">
        <Toggle label="Personalized recommendations" defaultChecked />
        <Toggle label="Share viewing data for research" />
      </Section>

      <Section title="Account">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="secondary">Change Password</Button>
          <Button variant="secondary">Download My Data</Button>
          <Button variant="secondary" onClick={logout}>
            <LogOut className="h-4 w-4" /> Logout
          </Button>
        </div>
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-card p-5 ring-1 ring-white/5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  defaultChecked,
}: {
  label: string;
  defaultChecked?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg px-1 py-1 text-sm">
      <span>{label}</span>
      <input
        type="checkbox"
        defaultChecked={defaultChecked}
        className="peer sr-only"
      />
      <span className="relative h-5 w-9 rounded-full bg-white/10 transition peer-checked:bg-primary">
        <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-4" />
      </span>
    </label>
  );
}
