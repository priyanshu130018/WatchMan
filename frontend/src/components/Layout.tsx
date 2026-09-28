import React, { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Search,
  User,
  Heart,
  History,
  LogOut,
  Menu,
  Film,
  Tv,
  MonitorPlay,
  Sparkles,
  ChevronDown,
  SlidersHorizontal,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { authService } from "@/services/auth";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { DesktopThemeToggle, MobileThemeToggle } from "@/components/ThemeToggle";

const PUBLIC_NAV_ITEMS = [
  { to: "/movie", label: "Movies", icon: Film },
  { to: "/web-series", label: "Web Series", icon: Tv },
  { to: "/ott", label: "OTT", icon: MonitorPlay },
] as const;

const AUTH_NAV_ITEMS = [
  { to: "/recommendation", label: "Recommend for You", icon: Sparkles },
  { to: "/movie", label: "Movies", icon: Film },
  { to: "/web-series", label: "Web Series", icon: Tv },
  { to: "/ott", label: "OTT", icon: MonitorPlay },
] as const;

const navLinkClass =
  "inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground";

export function Layout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const user = useAuthStore((s) => s.user);
  const authReady = useAuthStore((s) => s.authReady);
  const isLoading = useAuthStore((s) => s.isLoading);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  // Strictly gate navigation on settled auth state to avoid UI flicker
  const isLoggedIn = Boolean(authReady && !isLoading && user);
  const navItems = isLoggedIn ? AUTH_NAV_ITEMS : PUBLIC_NAV_ITEMS;

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      void navigate({ to: "/search", search: { q: searchQuery.trim() } as any });
      setSearchQuery("");
    }
  };

  const handleLogout = () => {
    authService.logout();
    clear();
    toast.success("Signed out.");
    void navigate({ to: "/" });
  };

  const initial = user?.email ? user.email[0].toUpperCase() : "U";

  return (
    <div className="min-h-screen bg-background text-foreground [background:radial-gradient(circle_at_80%_-10%,rgba(255,199,44,0.08),transparent_30%)]">
      {/* Skip link for keyboard / screen-reader users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4 sm:px-6 lg:gap-7 lg:px-7">
          {/* Brand */}
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2.5 text-[19px] font-extrabold tracking-tight text-foreground"
            aria-label="WatchMan — home"
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-[10px]">
              <img
                src="/watchman-mascot.png"
                alt=""
                className="h-full w-full object-cover"
                width={36}
                height={36}
              />
            </span>
            <span className="hidden sm:inline">WatchMan</span>
          </Link>

          {/* Desktop navigation */}
          <nav aria-label="Main" className="hidden items-center gap-6 lg:flex">
            {navItems.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className={navLinkClass}
                activeProps={{ className: "text-primary font-semibold" }}
              >
                <Icon size={15} aria-hidden="true" /> {label}
              </Link>
            ))}
          </nav>

          {/* Theme and Auth actions */}
          <div className="ml-auto flex items-center gap-2">
            <DesktopThemeToggle />
            {user ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  asChild
                  aria-label="Saved content"
                  title="Saved content"
                >
                  <Link to="/saved">
                    <Heart size={18} />
                  </Link>
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                      aria-label="Open account menu"
                    >
                      <Avatar className="h-8 w-8 border border-primary/60">
                        {user.avatar_url ? <AvatarImage src={user.avatar_url} alt="" /> : null}
                        <AvatarFallback>{initial}</AvatarFallback>
                      </Avatar>
                      <ChevronDown size={14} aria-hidden="true" className="text-muted-foreground" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel className="flex flex-col gap-0.5">
                      <span className="truncate text-sm font-semibold text-foreground">
                        {user.full_name || user.username || "User"}
                      </span>
                      <span className="truncate text-xs font-normal text-muted-foreground">
                        {user.email}
                      </span>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem asChild>
                      <Link to="/profile">
                        <User size={15} aria-hidden="true" /> Profile
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link to="/saved">
                        <Heart size={15} aria-hidden="true" /> Saved content
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link to="/history">
                        <History size={15} aria-hidden="true" /> Watch history
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={handleLogout}
                      className="text-destructive focus:text-destructive"
                    >
                      <LogOut size={15} aria-hidden="true" /> Sign out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : (
              <div className="hidden items-center gap-2 sm:flex">
                <Button asChild variant="outline" size="sm">
                  <Link to="/login">Login</Link>
                </Button>
                <Button asChild variant="brand" size="sm">
                  <Link to="/signup">Sign Up</Link>
                </Button>
              </div>
            )}

            {/* Mobile menu */}
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="lg:hidden"
                  aria-label="Open navigation menu"
                >
                  <Menu size={20} />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72">
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2.5">
                    <span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-[10px]">
                      <img
                        src="/watchman-mascot.png"
                        alt=""
                        className="h-full w-full object-cover"
                        width={32}
                        height={32}
                      />
                    </span>
                    WatchMan
                  </SheetTitle>
                </SheetHeader>
                <nav aria-label="Mobile" className="mt-6 flex flex-col gap-1">
                  {navItems.map(({ to, label, icon: Icon }) => (
                    <SheetClose asChild key={to}>
                      <Link
                        to={to}
                        className="flex items-center gap-3 rounded-md px-2 py-2.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                        activeProps={{ className: "bg-accent font-semibold text-primary" }}
                      >
                        <Icon size={17} aria-hidden="true" /> {label}
                      </Link>
                    </SheetClose>
                  ))}
                  <div className="my-2 h-px bg-border" />
                  <MobileThemeToggle />
                  <div className="my-2 h-px bg-border" />

                  {user ? (
                    <>
                      <SheetClose asChild>
                        <Link
                          to="/profile"
                          className="flex items-center gap-3 rounded-md px-2 py-2.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <User size={17} aria-hidden="true" /> Profile
                        </Link>
                      </SheetClose>
                      <SheetClose asChild>
                        <Link
                          to="/saved"
                          className="flex items-center gap-3 rounded-md px-2 py-2.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <Heart size={17} aria-hidden="true" /> Saved content
                        </Link>
                      </SheetClose>
                      <button
                        type="button"
                        onClick={() => {
                          setMobileOpen(false);
                          handleLogout();
                        }}
                        className="flex items-center gap-3 rounded-md px-2 py-2.5 text-left text-sm text-destructive hover:bg-accent"
                      >
                        <LogOut size={17} aria-hidden="true" /> Sign out
                      </button>
                    </>
                  ) : (
                    <div className="flex flex-col gap-2 pt-1">
                      <SheetClose asChild>
                        <Button asChild variant="outline" className="w-full">
                          <Link to="/login">Login</Link>
                        </Button>
                      </SheetClose>
                      <SheetClose asChild>
                        <Button asChild variant="brand" className="w-full">
                          <Link to="/signup">Create Account</Link>
                        </Button>
                      </SheetClose>
                    </div>
                  )}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      {/* Search bar directly below the navbar */}
      <div className="sticky top-16 z-30 border-b border-border bg-background/70 backdrop-blur-xl">
        <div className="mx-auto max-w-[1400px] px-4 py-3 sm:px-6 lg:px-7">
          <form
            onSubmit={handleSearchSubmit}
            role="search"
            className="mx-auto flex w-full max-w-2xl items-center gap-2"
          >
            <div className="relative flex-1">
              <label htmlFor="global-search" className="sr-only">
                Search movies and web series by name
              </label>
              <Search
                size={16}
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                id="global-search"
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search movies & web series by name..."
                className="h-10 pl-9"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              asChild
              className="h-10 shrink-0 gap-1.5 border-border bg-secondary font-medium text-foreground hover:border-primary/50 hover:bg-accent hover:text-primary transition-colors"
            >
              <Link
                to="/search"
                search={searchQuery.trim() ? { q: searchQuery.trim() } : undefined}
              >
                <SlidersHorizontal size={14} className="text-primary" aria-hidden="true" />
                <span className="hidden sm:inline">Advanced Search</span>
                <span className="sm:hidden">Advanced</span>
              </Link>
            </Button>
          </form>
        </div>
      </div>

      {/* Main content */}
      <main id="main-content">{children}</main>

      {/* Footer */}
      <footer className="mt-20 border-t border-border">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-bold text-foreground">WatchMan</span>
            <span>Cinematic movie &amp; web-series discovery platform</span>
          </p>
          <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2">
            {isLoggedIn && (
              <Link to="/recommendation" className="hover:text-foreground">
                Recommend for You
              </Link>
            )}
            <Link to="/movie" className="hover:text-foreground">
              Movies
            </Link>
            <Link to="/web-series" className="hover:text-foreground">
              Web Series
            </Link>
            <Link to="/ott" className="hover:text-foreground">
              OTT
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
