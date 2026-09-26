import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!apiBaseUrl || typeof apiBaseUrl !== "string" || !apiBaseUrl.trim()) {
  throw new Error(
    "ConfigurationError: Required frontend environment variable 'VITE_API_BASE_URL' is not configured.",
  );
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiErrorResponse {
  success: false;
  error: ApiErrorPayload;
}

export const API_BASE_URL = apiBaseUrl.trim();
export const api = axios.create({ baseURL: API_BASE_URL, timeout: 20000 });

let accessToken: string | null = null;
let refreshTokenGetter: (() => string | null) | null = null;
let sessionClearer: (() => void) | null = null;
let sessionUpdater: ((accessToken: string, refreshToken?: string | null) => void) | null = null;
// Optional provider-supplied refresh (e.g. Supabase). When set, it is used
// instead of calling the local `/auth/refresh` endpoint.
let sessionRefresher:
  | ((
      refreshToken: string | null,
    ) => Promise<{ access_token: string; refresh_token?: string | null }>)
  | null = null;

export const setApiToken = (token: string | null) => {
  accessToken = token;
};

export const getApiToken = () => accessToken;

export const registerAuthHandlers = (handlers: {
  getRefreshToken: () => string | null;
  updateSession: (accessToken: string, refreshToken?: string | null) => void;
  clearSession: () => void;
  refreshSession?: (
    refreshToken: string | null,
  ) => Promise<{ access_token: string; refresh_token?: string | null }>;
}) => {
  refreshTokenGetter = handlers.getRefreshToken;
  sessionUpdater = handlers.updateSession;
  sessionClearer = handlers.clearSession;
  sessionRefresher = handlers.refreshSession ?? null;
};

// Coordinated token refresh state
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Attach Authorization header and Request ID
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// Response interceptor with coordinated token refresh queue
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Standardize error payload
    if (error.response?.data) {
      const data = error.response.data as Record<string, any>;
      if (data.error && typeof data.error.message === "string") {
        if (!data.detail) {
          data.detail = data.error.message;
        }
      }
    }

    // Check if error is 401 and request can be retried with token refresh
    const isAuthEndpoint =
      originalRequest?.url?.includes("/auth/login") ||
      originalRequest?.url?.includes("/auth/register") ||
      originalRequest?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && !originalRequest?._retry && !isAuthEndpoint) {
      const currentRefreshToken = refreshTokenGetter ? refreshTokenGetter() : null;

      if (!currentRefreshToken) {
        if (sessionClearer) sessionClearer();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue the request until the ongoing refresh completes
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
            }
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        let newAccessToken: string;
        let newRefreshToken: string | null | undefined;

        if (sessionRefresher) {
          // Provider-managed refresh (e.g. Supabase Auth).
          const refreshed = await sessionRefresher(currentRefreshToken);
          newAccessToken = refreshed.access_token;
          newRefreshToken = refreshed.refresh_token;
        } else {
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: currentRefreshToken,
          });
          newAccessToken = data.access_token;
          newRefreshToken = data.refresh_token;
        }

        setApiToken(newAccessToken);
        if (sessionUpdater) {
          sessionUpdater(newAccessToken, newRefreshToken);
        }

        processQueue(null, newAccessToken);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        }
        return api(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        if (sessionClearer) {
          sessionClearer();
        }
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const errorData = error.response?.data as ApiErrorResponse | undefined;
    if (errorData?.error?.message) {
      return errorData.error.message;
    }
    if (typeof (error.response?.data as { detail?: string })?.detail === "string") {
      return (error.response?.data as { detail: string }).detail;
    }
    return error.message || "An unexpected network error occurred.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || "An unexpected error occurred.");
}
