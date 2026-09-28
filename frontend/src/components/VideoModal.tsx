import React, { useEffect, useRef, useState } from "react";
import { Maximize, Minimize, X } from "lucide-react";

import { type VideoItem } from "@/types/content";
import { Dialog, DialogContent } from "@/components/ui/dialog";

export interface VideoModalProps {
  isOpen: boolean;
  onClose: () => void;
  video: VideoItem | null;
  title: string;
}

export function VideoModal({ isOpen, onClose, video, title }: VideoModalProps) {
  const modalContainerRef = useRef<HTMLDivElement>(null);
  const [isNativeFullscreen, setIsNativeFullscreen] = useState(false);

  // Monitor native HTML5 fullscreen state
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsNativeFullscreen(Boolean(document.fullscreenElement));
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  // Exit native fullscreen if modal is closed
  useEffect(() => {
    if (!isOpen && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  }, [isOpen]);

  // Keyboard shortcut listener ('f' for native fullscreen toggle)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        toggleNativeFullscreen();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const toggleNativeFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        if (modalContainerRef.current?.requestFullscreen) {
          await modalContainerRef.current.requestFullscreen();
        }
      } else {
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        }
      }
    } catch (err) {
      console.warn("Fullscreen toggle unavailable or denied by browser:", err);
    }
  };

  if (!video) return null;

  const isYouTube = video.site.toLowerCase() === "youtube";
  const embedUrl = isYouTube
    ? `https://www.youtube-nocookie.com/embed/${video.key}?autoplay=1&rel=0&modestbranding=1&enablejsapi=1`
    : null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        ref={modalContainerRef}
        fullscreen
        hideClose
        className="flex h-screen w-screen flex-col overflow-hidden border-0 bg-black p-0"
        aria-label={`${title} trailer player`}
      >
        {/* Top Control Bar */}
        <div className="z-20 flex h-14 w-full shrink-0 items-center justify-between border-b border-white/10 bg-black/90 px-4 sm:px-6 backdrop-blur-md">
          <div className="flex items-center gap-3 min-w-0 pr-4">
            <span className="shrink-0 rounded bg-watchman-yellow/20 px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-watchman-yellow border border-watchman-yellow/30">
              Trailer
            </span>
            <h2 className="truncate text-sm sm:text-base font-semibold text-white">
              {video.name || `${title} — Official Trailer`}
            </h2>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={toggleNativeFullscreen}
              className="rounded-lg p-2 text-white/70 hover:text-white hover:bg-white/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title={isNativeFullscreen ? "Exit full screen (f)" : "Full screen (f)"}
              aria-label={isNativeFullscreen ? "Exit full screen" : "Full screen"}
            >
              {isNativeFullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-white/70 hover:text-white hover:bg-white/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title="Close trailer (Esc)"
              aria-label="Close trailer"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Cinematic Video Player Canvas */}
        <div className="flex-1 min-h-0 w-full flex items-center justify-center p-2 sm:p-4 md:p-6 lg:p-8 bg-black">
          <div className="relative w-full h-full max-w-[calc((100vh-80px)*16/9)] max-h-[calc(100vh-80px)] aspect-video rounded-xl overflow-hidden shadow-2xl bg-black border border-white/10 flex items-center justify-center">
            {embedUrl ? (
              <iframe
                src={embedUrl}
                title={video.name || `${title} — Trailer`}
                className="h-full w-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
                allowFullScreen
              />
            ) : (
              <div className="flex h-full items-center justify-center text-muted-foreground p-6 text-center">
                Video source ({video.site}) is not supported for embedded playback.
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
