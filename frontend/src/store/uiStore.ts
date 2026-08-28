import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light" | "system";

interface Filters {
  genres: string[];
  languages: string[];
  platforms: string[];
  year: string;
  minRating: number;
}

interface UIState {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  theme: Theme;
  setTheme: (t: Theme) => void;

  filters: Filters;
  setFilters: (f: Partial<Filters>) => void;
  clearFilters: () => void;
}

const defaultFilters: Filters = {
  genres: [],
  languages: [],
  platforms: [],
  year: "",
  minRating: 0,
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: false,
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

      theme: "dark",
      setTheme: (theme) => set({ theme }),

      filters: defaultFilters,
      setFilters: (f) => set((s) => ({ filters: { ...s.filters, ...f } })),
      clearFilters: () => set({ filters: defaultFilters }),
    }),
    {
      name: "rabbit-ui",
      partialize: (s) => ({ theme: s.theme, filters: s.filters }),
    },
  ),
);
