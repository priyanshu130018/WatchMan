import { Sun, Moon, Laptop } from "lucide-react";
import { useThemeStore } from "@/store/themeStore";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function DesktopThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useThemeStore();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="relative h-9 w-9 rounded-lg border-border bg-background hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Current theme: ${theme}. Click to change theme.`}
          title={`Theme: ${theme}`}
        >
          {resolvedTheme === "dark" ? (
            <Moon className="h-4 w-4 text-foreground transition-transform" aria-hidden="true" />
          ) : (
            <Sun className="h-4 w-4 text-foreground transition-transform" aria-hidden="true" />
          )}
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        <DropdownMenuItem
          onClick={() => setTheme("light")}
          className={theme === "light" ? "font-semibold text-primary" : ""}
        >
          <Sun className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>Light</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setTheme("dark")}
          className={theme === "dark" ? "font-semibold text-primary" : ""}
        >
          <Moon className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>Dark</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setTheme("system")}
          className={theme === "system" ? "font-semibold text-primary" : ""}
        >
          <Laptop className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>System</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function MobileThemeToggle() {
  const { theme, setTheme } = useThemeStore();

  return (
    <div className="flex flex-col gap-1.5 pt-2">
      <span className="px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Theme Appearance
      </span>
      <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-muted/60 p-1">
        <button
          type="button"
          onClick={() => setTheme("light")}
          className={`flex items-center justify-center gap-1.5 rounded-md py-2 text-xs font-medium transition-colors ${
            theme === "light"
              ? "bg-background text-foreground shadow-sm font-semibold"
              : "text-muted-foreground hover:text-foreground"
          }`}
          aria-pressed={theme === "light"}
        >
          <Sun className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Light</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme("dark")}
          className={`flex items-center justify-center gap-1.5 rounded-md py-2 text-xs font-medium transition-colors ${
            theme === "dark"
              ? "bg-background text-foreground shadow-sm font-semibold"
              : "text-muted-foreground hover:text-foreground"
          }`}
          aria-pressed={theme === "dark"}
        >
          <Moon className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Dark</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme("system")}
          className={`flex items-center justify-center gap-1.5 rounded-md py-2 text-xs font-medium transition-colors ${
            theme === "system"
              ? "bg-background text-foreground shadow-sm font-semibold"
              : "text-muted-foreground hover:text-foreground"
          }`}
          aria-pressed={theme === "system"}
        >
          <Laptop className="h-3.5 w-3.5" aria-hidden="true" />
          <span>System</span>
        </button>
      </div>
    </div>
  );
}
