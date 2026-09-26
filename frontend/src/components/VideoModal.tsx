import { type VideoItem } from "@/types/content";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export interface VideoModalProps {
  isOpen: boolean;
  onClose: () => void;
  video: VideoItem | null;
  title: string;
}

export function VideoModal({ isOpen, onClose, video, title }: VideoModalProps) {
  if (!video) return null;

  const isYouTube = video.site.toLowerCase() === "youtube";
  const embedUrl = isYouTube
    ? `https://www.youtube-nocookie.com/embed/${video.key}?autoplay=1&rel=0`
    : null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl overflow-hidden p-0" aria-label={`${title} trailer`}>
        <DialogHeader className="border-b border-border bg-secondary/40 px-4 py-3">
          <DialogTitle className="line-clamp-1 pr-8 text-base font-semibold text-foreground">
            {video.name || `${title} — Trailer`}
          </DialogTitle>
        </DialogHeader>

        <div className="aspect-video w-full bg-black">
          {embedUrl ? (
            <iframe
              src={embedUrl}
              title={video.name || title}
              className="h-full w-full border-0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              Video source not supported for playback.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
