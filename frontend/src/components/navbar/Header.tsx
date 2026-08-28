import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { Menu, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useUIStore } from "@/store/uiStore";
import { RabbitLogo } from "./RabbitLogo";

export function Header() {
  const toggle = useUIStore((s) => s.toggleSidebar);
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [q, setQ] = useState("");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    // reset input on route change away from search
    if (!pathname.startsWith("/search")) setQ("");
  }, [pathname]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    navigate({ to: "/search", search: { q: q.trim() } as never });
  };

  return (
    <header
      className={`sticky top-0 z-40 transition-all ${
        scrolled
          ? "border-b border-white/5 bg-background/80 backdrop-blur-xl"
          : "bg-gradient-to-b from-background to-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
        <Link
          to="/"
          className="flex items-center gap-2 shrink-0"
          aria-label="Rabbit home"
        >
          <RabbitLogo className="h-8 w-8" />
          <span className="hidden text-lg font-bold tracking-tight sm:block">
            <span className="text-gradient-rabbit">Rabbit</span>
          </span>
        </Link>

        <form
          onSubmit={submit}
          className="relative mx-2 flex-1 min-w-0 max-w-2xl"
          role="search"
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search movies, actors, directors..."
            aria-label="Search"
            className="w-full rounded-full border border-white/10 bg-white/5 py-2.5 pl-10 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/60 focus:border-transparent"
          />
        </form>

        <button
          type="button"
          onClick={toggle}
          aria-label="Open menu"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/5 text-foreground hover:bg-white/10 transition"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
}
