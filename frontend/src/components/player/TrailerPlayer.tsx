export function TrailerPlayer({ url, title }: { url?: string; title?: string }) {
  if (!url) return null;
  const embed = toEmbed(url);
  return (
    <div className="overflow-hidden rounded-2xl bg-black ring-1 ring-white/10 aspect-video">
      <iframe
        src={embed}
        title={title ?? "Trailer"}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className="h-full w-full"
      />
    </div>
  );
}

function toEmbed(url: string) {
  try {
    const u = new URL(url);
    if (u.hostname.includes("youtube.com")) {
      const id = u.searchParams.get("v");
      if (id) return `https://www.youtube.com/embed/${id}`;
    }
    if (u.hostname === "youtu.be") {
      return `https://www.youtube.com/embed${u.pathname}`;
    }
    if (u.hostname.includes("vimeo.com")) {
      return `https://player.vimeo.com/video${u.pathname}`;
    }
    return url;
  } catch {
    return url;
  }
}
