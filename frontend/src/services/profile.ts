import { api } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import type { User } from "@/types/user";

export const profileService = {
  get: async (): Promise<User> => {
    const { data } = await api.get<User>(endpoints.profile);
    return data;
  },
  update: async (payload: Partial<User>): Promise<User> => {
    const { data } = await api.put<User>(endpoints.profile, payload);
    return data;
  },
};
