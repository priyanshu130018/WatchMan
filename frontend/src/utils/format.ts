export const year = (d?: string | null) => d?.slice(0, 4) || "—";

export const rating = (n?: number | null) =>
  typeof n === "number" && !isNaN(n) ? n.toFixed(1) : "—";

export const runtime = (n?: number | null) => (n ? `${Math.floor(n / 60)}h ${n % 60}m` : "—");

export const formatDate = (d?: string | null) => {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return d;
  }
};

export const formatTimeAgo = (d?: string | null) => {
  if (!d) return "just now";
  try {
    const date = new Date(d);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo ago`;
    const years = Math.floor(days / 365);
    return `${years}y ago`;
  } catch {
    return "recently";
  }
};
