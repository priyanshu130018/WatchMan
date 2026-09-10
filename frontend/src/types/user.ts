export type User = { id: string; email: string; full_name?: string | null; username?: string | null };
export type AuthResponse = { access_token: string; token_type: string };
