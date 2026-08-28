export function formatRuntime(min?: number) {
  if (!min) return "";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

export function formatYear(date?: string, year?: number) {
  if (year) return String(year);
  if (!date) return "";
  return date.slice(0, 4);
}

export function formatRating(r?: number, digits = 1) {
  if (r == null || Number.isNaN(r)) return "—";
  return r.toFixed(digits);
}

export function formatMatch(m?: number) {
  if (m == null) return null;
  return `${Math.round(m)}%`;
}
