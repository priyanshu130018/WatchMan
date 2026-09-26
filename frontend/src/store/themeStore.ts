import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "watchman-theme";

interface ThemeState {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    return getSystemTheme();
  }
  return theme;
}

function applyThemeToDocument(resolved: "light" | "dark") {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
    root.classList.remove("light");
    root.style.colorScheme = "dark";
  } else {
    root.classList.add("light");
    root.classList.remove("dark");
    root.style.colorScheme = "light";
  }
  root.setAttribute("data-theme", resolved);
}

const fallbackStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "dark",
      resolvedTheme: "dark",
      setTheme: (theme: Theme) => {
        const resolved = resolveTheme(theme);
        applyThemeToDocument(resolved);
        set({ theme, resolvedTheme: resolved });
      },
      toggleTheme: () => {
        const current = get().resolvedTheme;
        const next = current === "dark" ? "light" : "dark";
        get().setTheme(next);
      },
    }),
    {
      name: THEME_STORAGE_KEY,
      storage: createJSONStorage(() =>
        typeof window !== "undefined" && window.localStorage
          ? window.localStorage
          : fallbackStorage,
      ),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const resolved = resolveTheme(state.theme);
        state.resolvedTheme = resolved;
        applyThemeToDocument(resolved);
      },
    },
  ),
);

// Register system theme change listener in browser
if (typeof window !== "undefined" && window.matchMedia) {
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const handleMediaChange = () => {
    const { theme, setTheme } = useThemeStore.getState();
    if (theme === "system") {
      setTheme("system");
    }
  };
  if (mql.addEventListener) {
    mql.addEventListener("change", handleMediaChange);
  } else if ("addListener" in mql) {
    (mql as any).addListener(handleMediaChange);
  }
}
