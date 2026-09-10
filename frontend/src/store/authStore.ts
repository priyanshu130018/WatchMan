import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { setApiToken } from '@/lib/api';
import type { User } from '@/types/user';

type State = { token: string | null; user: User | null; setSession: (token: string, user: User) => void; clear: () => void };
export const useAuthStore = create<State>()(persist((set) => ({
  token: null, user: null,
  setSession: (token, user) => { setApiToken(token); set({ token, user }); },
  clear: () => { setApiToken(null); set({ token: null, user: null }); },
}), { name: 'watchman-auth' }));

const persisted = useAuthStore.getState();
if (persisted.token) setApiToken(persisted.token);
