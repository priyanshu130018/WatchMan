import { api } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import type {
  AuthResponse,
  LoginPayload,
  RegisterPayload,
  User,
} from "@/types/user";

export const authService = {
  login: async (payload: LoginPayload): Promise<AuthResponse> => {
    const { data } = await api.post<AuthResponse>(endpoints.auth.login, payload);
    return data;
  },
  register: async (payload: RegisterPayload): Promise<AuthResponse> => {
    const { data } = await api.post<AuthResponse>(
      endpoints.auth.register,
      payload,
    );
    return data;
  },
  logout: async (): Promise<void> => {
    await api.post(endpoints.auth.logout);
  },
  googleUrl: () => {
    const base =
      (typeof import.meta !== "undefined" &&
        import.meta.env?.VITE_API_BASE_URL) ||
      "/api";
    return `${base}${endpoints.auth.google}`;
  },
  me: async (): Promise<User> => {
    const { data } = await api.get<User>(endpoints.auth.me);
    return data;
  },
};
