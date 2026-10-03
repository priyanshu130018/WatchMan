import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setApiToken, registerAuthHandlers } from "@/lib/api";
import type { User } from "@/types/user";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isLoading: boolean;
  authReady: boolean;
  setSession: (token: string, user: User, refreshToken?: string | null) => void;
  setUser: (user: User) => void;
  updateTokens: (token: string, refreshToken?: string | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      isLoading: false,
      authReady: true,
      setSession: (token, user, refreshToken = null) => {
        setApiToken(token);
        set({ token, user, refreshToken: refreshToken ?? null, authReady: true });
      },
      setUser: (user) => set({ user }),
      updateTokens: (token, refreshToken = null) => {
        setApiToken(token);
        set((state) => ({
          token,
          refreshToken: refreshToken ?? state.refreshToken,
        }));
      },
      clear: () => {
        setApiToken(null);
        set({ token: null, refreshToken: null, user: null, authReady: true });
      },
    }),
    {
      name: "watchman-auth",
      // Never persist transient flags — they must be recomputed each load.
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
);

// Register coordinated auth handlers for axios interceptor
registerAuthHandlers({
  getRefreshToken: () => useAuthStore.getState().refreshToken,
  updateSession: (accessToken, refreshToken) => {
    useAuthStore.getState().updateTokens(accessToken, refreshToken);
  },
  clearSession: () => {
    useAuthStore.getState().clear();
  },
});

// Synchronize persisted token into axios on initial application load
const initialAuth = useAuthStore.getState();
if (initialAuth.token) {
  setApiToken(initialAuth.token);
}
