import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const rawUrl = import.meta.env.VITE_SUPABASE_URL;
const rawKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

const url = typeof rawUrl === "string" ? rawUrl.trim() : "";
const key = typeof rawKey === "string" ? rawKey.trim() : "";

// Supabase client is initialized only when valid non-empty public configuration is provided
export const supabase: SupabaseClient | null = url && key ? createClient(url, key) : null;
