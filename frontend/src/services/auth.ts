import { api, setApiToken, API_BASE_URL } from "@/lib/api";
import type { AuthResponse, User } from "@/types/user";

export const AUTH_PROVIDER = "local";
export const isSupabaseAuth = false;

/** Fetch the WatchMan user record for the currently attached access token. */
async function fetchCurrentUser(): Promise<User> {
  console.log(`[WatchMan Auth] Fetching /auth/me from ${API_BASE_URL}...`);
  const { data } = await api.get<User>("/auth/me");
  console.log("[WatchMan Auth] /auth/me response:", { id: data.id, email: data.email, username: data.username });
  return data;
}

export const authService = {
  async login(email: string, password: string): Promise<AuthResponse> {
    console.log(`[WatchMan Auth] authService.login called for email=${email}`);
    console.log(`[WatchMan Auth] Target URL: ${API_BASE_URL}/auth/login`);
    try {
      const response = await api.post<AuthResponse>("/auth/login", { email, password });
      console.log(`[WatchMan Auth] Login response status: ${response.status}`);
      console.log("[WatchMan Auth] Login response body:", {
        token_type: response.data.token_type,
        user: response.data.user,
        has_access_token: !!response.data.access_token,
        has_refresh_token: !!response.data.refresh_token,
      });
      setApiToken(response.data.access_token);
      return response.data;
    } catch (err) {
      console.error("[WatchMan Auth] Login request failed:", err);
      throw err;
    }
  },

  async register(
    email: string,
    password: string,
    full_name?: string,
    username?: string,
  ): Promise<AuthResponse> {
    console.log(`[WatchMan Auth] authService.register called for email=${email}`);
    console.log(`[WatchMan Auth] Target URL: ${API_BASE_URL}/auth/register`);
    try {
      const response = await api.post<AuthResponse>("/auth/register", {
        email,
        password,
        full_name: full_name || undefined,
        username: username || undefined,
      });
      console.log(`[WatchMan Auth] Register response status: ${response.status}`);
      setApiToken(response.data.access_token);
      return response.data;
    } catch (err) {
      console.error("[WatchMan Auth] Register request failed:", err);
      throw err;
    }
  },

  async refresh(refreshToken: string): Promise<AuthResponse> {
    const { data } = await api.post<AuthResponse>("/auth/refresh", {
      refresh_token: refreshToken,
    });
    setApiToken(data.access_token);
    return data;
  },

  async me(): Promise<User> {
    return fetchCurrentUser();
  },

  async requestPasswordReset(_email: string, _redirectTo?: string): Promise<void> {
    throw new Error("Password reset is not configured for local authentication.");
  },

  async updatePassword(_newPassword: string): Promise<void> {
    throw new Error("Password update is not configured for local authentication.");
  },

  logout(): void {
    try {
      api.post("/auth/logout").catch(() => {});
    } catch {
      // Best-effort logout notification
    }
    setApiToken(null);
  },
};
