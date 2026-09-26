import { api, setApiToken } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { AuthResponse, User } from "@/types/user";

/**
 * Authentication provider selection (build-time).
 *
 *   VITE_AUTH_PROVIDER=supabase  -> production: Supabase Auth owns identity.
 *   VITE_AUTH_PROVIDER=local (or unset) -> development: legacy local JWT API.
 *
 * In the Supabase path the browser authenticates against Supabase directly; the
 * resulting Supabase access token is what we attach to API requests, and the
 * FastAPI backend validates that token. No local password ever reaches the API.
 */
export const AUTH_PROVIDER = (
  (import.meta.env.VITE_AUTH_PROVIDER as string | undefined)?.trim() || "local"
).toLowerCase();

export const isSupabaseAuth = AUTH_PROVIDER === "supabase";

function requireSupabaseClient() {
  if (!supabase) {
    throw new Error(
      "ConfigurationError: Supabase auth is enabled (VITE_AUTH_PROVIDER=supabase) " +
        "but VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY are not configured.",
    );
  }
  return supabase;
}

/** Fetch the WatchMan user record for the currently attached access token. */
async function fetchCurrentUser(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export const authService = {
  async login(email: string, password: string): Promise<AuthResponse> {
    if (isSupabaseAuth) {
      const client = requireSupabaseClient();
      const { data, error } = await client.auth.signInWithPassword({ email, password });
      if (error || !data.session) {
        throw new Error(error?.message || "Invalid email or password.");
      }
      setApiToken(data.session.access_token);
      const user = await fetchCurrentUser();
      return {
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
        token_type: "bearer",
        user,
      };
    }
    const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
    setApiToken(data.access_token);
    return data;
  },

  async register(
    email: string,
    password: string,
    full_name?: string,
    username?: string,
  ): Promise<AuthResponse> {
    if (isSupabaseAuth) {
      const client = requireSupabaseClient();
      const { data, error } = await client.auth.signUp({
        email,
        password,
        options: { data: { full_name: full_name || null, username: username || null } },
      });
      if (error) {
        throw new Error(error.message);
      }
      // When email confirmation is enabled there is no session yet.
      if (!data.session) {
        return { access_token: "", refresh_token: null, token_type: "bearer", user: null };
      }
      setApiToken(data.session.access_token);
      const user = await fetchCurrentUser();
      return {
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
        token_type: "bearer",
        user,
      };
    }
    const { data } = await api.post<AuthResponse>("/auth/register", {
      email,
      password,
      full_name: full_name || undefined,
      username: username || undefined,
    });
    setApiToken(data.access_token);
    return data;
  },

  async refresh(refreshToken: string): Promise<AuthResponse> {
    if (isSupabaseAuth) {
      const client = requireSupabaseClient();
      const { data, error } = await client.auth.refreshSession(
        refreshToken ? { refresh_token: refreshToken } : undefined,
      );
      if (error || !data.session) {
        throw new Error(error?.message || "Session refresh failed.");
      }
      setApiToken(data.session.access_token);
      return {
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
        token_type: "bearer",
        user: null,
      };
    }
    const { data } = await api.post<AuthResponse>("/auth/refresh", {
      refresh_token: refreshToken,
    });
    setApiToken(data.access_token);
    return data;
  },

  async me(): Promise<User> {
    return fetchCurrentUser();
  },

  /** Send a password-reset email via Supabase Auth (Supabase mode only). */
  async requestPasswordReset(email: string, redirectTo?: string): Promise<void> {
    if (!isSupabaseAuth) {
      throw new Error("Password reset is handled by Supabase Auth and is not enabled.");
    }
    const client = requireSupabaseClient();
    const { error } = await client.auth.resetPasswordForEmail(email, {
      redirectTo: redirectTo || `${window.location.origin}/reset-password`,
    });
    if (error) {
      throw new Error(error.message);
    }
  },

  /** Update the signed-in user's password (used on the reset-password screen). */
  async updatePassword(newPassword: string): Promise<void> {
    if (!isSupabaseAuth) {
      throw new Error("Password update is handled by Supabase Auth and is not enabled.");
    }
    const client = requireSupabaseClient();
    const { error } = await client.auth.updateUser({ password: newPassword });
    if (error) {
      throw new Error(error.message);
    }
  },

  logout(): void {
    if (isSupabaseAuth) {
      if (supabase) {
        supabase.auth.signOut().catch(() => {});
      }
      setApiToken(null);
      return;
    }
    try {
      api.post("/auth/logout").catch(() => {});
    } catch {
      // Best-effort logout notification
    }
    setApiToken(null);
  },
};
