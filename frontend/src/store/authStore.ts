import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setApiToken, registerAuthHandlers } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { authService, isSupabaseAuth } from "@/services/auth";
import type { User } from "@/types/user";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isLoading: boolean;
  /**
   * True once the initial session-restoration attempt has settled. In Supabase
   * mode this flips after `getSession()` resolves (and the user record, if any,
   * has been hydrated); in local mode it is true immediately. Route guards use
   * this to avoid flashing a "sign in" screen while a valid session is still
   * being restored.
   */
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
      // Local mode restores synchronously; Supabase mode toggles this below.
      authReady: !isSupabaseAuth,
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
  // In Supabase mode, token refresh is delegated to the Supabase client.
  refreshSession:
    isSupabaseAuth && supabase
      ? async () => {
          const client = supabase;
          if (!client) throw new Error("Supabase client unavailable.");
          const { data, error } = await client.auth.refreshSession();
          if (error || !data.session) {
            throw error || new Error("Supabase session refresh failed.");
          }
          return {
            access_token: data.session.access_token,
            refresh_token: data.session.refresh_token,
          };
        }
      : undefined,
});

if (isSupabaseAuth && supabase) {
  // Supabase owns the session lifecycle: hydrate on load and keep the store +
  // axios token in sync as Supabase auto-refreshes or the user signs out.
  supabase.auth
    .getSession()
    .then(async ({ data }) => {
      const session = data.session;
      if (session) {
        setApiToken(session.access_token);
        useAuthStore.setState({
          token: session.access_token,
          refreshToken: session.refresh_token,
        });
        // A valid session may exist without a persisted user record (e.g. after
        // localStorage was cleared or the token refreshed in another tab). Fetch
        // the WatchMan user so the UI reflects the authenticated identity.
        if (!useAuthStore.getState().user) {
          try {
            const user = await authService.me();
            useAuthStore.getState().setUser(user);
          } catch {
            // Leave user null; the API layer will drive re-auth on 401.
          }
        }
      }
    })
    .catch(() => {
      // Ignore: treated as "no session".
    })
    .finally(() => {
      useAuthStore.setState({ authReady: true });
    });

  supabase.auth.onAuthStateChange((_event, session) => {
    if (session) {
      setApiToken(session.access_token);
      useAuthStore.setState({
        token: session.access_token,
        refreshToken: session.refresh_token,
        authReady: true,
      });
      if (!useAuthStore.getState().user) {
        authService
          .me()
          .then((user) => useAuthStore.getState().setUser(user))
          .catch(() => {});
      }
    } else {
      useAuthStore.getState().clear();
    }
  });
} else {
  // Local dev path: synchronize the persisted token into axios on load.
  const initialAuth = useAuthStore.getState();
  if (initialAuth.token) {
    setApiToken(initialAuth.token);
  }
}
