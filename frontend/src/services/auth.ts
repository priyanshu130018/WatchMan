import { api, setApiToken } from '@/lib/api';
import type { AuthResponse, User } from '@/types/user';

export const authService = {
  async login(email: string, password: string) {
    const { data } = await api.post<AuthResponse>('/auth/login', { email, password });
    setApiToken(data.access_token); return data;
  },
  async register(email: string, password: string, full_name?: string) {
    const { data } = await api.post<AuthResponse>('/auth/register', { email, password, full_name });
    setApiToken(data.access_token); return data;
  },
  async me() { const { data } = await api.get<User>('/auth/me'); return data; },
  logout() { setApiToken(null); },
};
