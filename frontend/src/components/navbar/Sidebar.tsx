import { AnimatePresence, motion } from "framer-motion";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Heart,
  History as HistoryIcon,
  LogIn,
  LogOut,
  Settings as SettingsIcon,
  User as UserIcon,
  UserPlus,
  X,
} from "lucide-react";
import { useUIStore } from "@/store/uiStore";
import { useAuthStore } from "@/store/authStore";
import { authService } from "@/services/auth";
import { GENRE_OPTIONS, LANGUAGE_OPTIONS, PLATFORM_OPTIONS, YEAR_OPTIONS } from "@/utils/genres";
import { Button } from "@/components/ui/button";

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
          ? "border-primary bg-primary/20 text-foreground"
          : "border-white/10 bg-white/5 text-muted-foreground hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}

export function Sidebar() {
  const open = useUIStore((s) => s.sidebarOpen);
  const setOpen = useUIStore((s) => s.setSidebarOpen);
  const filters = useUIStore((s) => s.filters);
  const setFilters = useUIStore((s) => s.setFilters);
  const clearFilters = useUIStore((s) => s.clearFilters);
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  const toggle = (
    key: "genres" | "languages" | "platforms",
    v: string,
  ) => {
    const cur = filters[key];
    setFilters({
      [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v],
    } as never);
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch {
      /* ignore */
    }
    clear();
    setOpen(false);
    navigate({ to: "/" });
  };

  const applyFilters = () => {
    setOpen(false);
    navigate({
      to: "/search",
      search: {
        q: "",
        genre: filters.genres.join(","),
        language: filters.languages.join(","),
        platform: filters.platforms.join(","),
        year: filters.year,
      } as never,
    });
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col overflow-y-auto border-l border-white/10 bg-sidebar text-sidebar-foreground shadow-2xl"
            role="dialog"
            aria-label="Menu"
          >
            <div className="flex items-center justify-between border-b border-white/5 p-4">
              <span className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                Menu
              </span>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close menu"
                className="grid h-9 w-9 place-items-center rounded-full bg-white/5 hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4">
              {user ? (
                <div className="flex items-center gap-3 rounded-2xl glass p-3">
                  <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full gradient-rabbit text-lg font-bold">
                    {user.username?.[0]?.toUpperCase() ?? "U"}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{user.username}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {user.email}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  <Link to="/login" onClick={() => setOpen(false)}>
                    <Button variant="secondary" className="w-full">
                      <LogIn className="h-4 w-4" /> Sign In
                    </Button>
                  </Link>
                  <Link to="/signup" onClick={() => setOpen(false)}>
                    <Button className="w-full gradient-rabbit border-0">
                      <UserPlus className="h-4 w-4" /> Sign Up
                    </Button>
                  </Link>
                </div>
              )}
            </div>

            {user && (
              <nav className="flex flex-col gap-1 px-2">
                <SideLink to="/profile" icon={<UserIcon className="h-4 w-4" />} onClick={() => setOpen(false)}>Profile</SideLink>
                <SideLink to="/favorites" icon={<Heart className="h-4 w-4" />} onClick={() => setOpen(false)}>Favorites</SideLink>
                <SideLink to="/history" icon={<HistoryIcon className="h-4 w-4" />} onClick={() => setOpen(false)}>History</SideLink>
                <SideLink to="/settings" icon={<SettingsIcon className="h-4 w-4" />} onClick={() => setOpen(false)}>Settings</SideLink>
                <button
                  onClick={logout}
                  className="mt-1 flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-destructive hover:bg-destructive/10"
                >
                  <LogOut className="h-4 w-4" /> Logout
                </button>
              </nav>
            )}

            <div className="mt-6 space-y-5 border-t border-white/5 px-4 py-5">
              <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Movie Filters
              </h3>

              <FilterGroup label="Genres">
                {GENRE_OPTIONS.map((g) => (
                  <Chip key={g} active={filters.genres.includes(g)} onClick={() => toggle("genres", g)}>
                    {g}
                  </Chip>
                ))}
              </FilterGroup>

              <FilterGroup label="Languages">
                {LANGUAGE_OPTIONS.map((l) => (
                  <Chip key={l} active={filters.languages.includes(l)} onClick={() => toggle("languages", l)}>
                    {l}
                  </Chip>
                ))}
              </FilterGroup>

              <FilterGroup label="Streaming Platforms">
                {PLATFORM_OPTIONS.map((p) => (
                  <Chip key={p} active={filters.platforms.includes(p)} onClick={() => toggle("platforms", p)}>
                    {p}
                  </Chip>
                ))}
              </FilterGroup>

              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Year</label>
                <select
                  value={filters.year}
                  onChange={(e) => setFilters({ year: e.target.value })}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm"
                >
                  <option value="">Any</option>
                  {YEAR_OPTIONS.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  Min IMDb rating: <span className="text-foreground">{filters.minRating.toFixed(1)}</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={10}
                  step={0.5}
                  value={filters.minRating}
                  onChange={(e) => setFilters({ minRating: Number(e.target.value) })}
                  className="w-full accent-[var(--rabbit-red)]"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <Button onClick={applyFilters} className="flex-1 gradient-rabbit border-0">
                  Apply Filters
                </Button>
                <Button onClick={clearFilters} variant="secondary" className="flex-1">
                  Clear
                </Button>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function SideLink({
  to,
  icon,
  children,
  onClick,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <Link
      to={to}
      onClick={onClick}
      className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-foreground/90 hover:bg-white/5"
    >
      {icon}
      <span>{children}</span>
    </Link>
  );
}

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
