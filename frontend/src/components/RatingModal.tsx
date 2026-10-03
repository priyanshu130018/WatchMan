import React, { useEffect, useState } from "react";
import { Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface RatingModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  initialRating?: number;
  onRate: (rating: number) => Promise<void>;
}

const RATING_DESCRIPTIONS: Record<number, string> = {
  1: "Appalling",
  2: "Terrible",
  3: "Very Bad",
  4: "Bad",
  5: "Average",
  6: "Fine",
  7: "Good",
  8: "Very Good",
  9: "Great",
  10: "Masterpiece",
};

export function RatingModal({
  isOpen,
  onClose,
  title,
  initialRating = 0,
  onRate,
}: RatingModalProps) {
  const [selectedRating, setSelectedRating] = useState(initialRating);
  const [hoverRating, setHoverRating] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setSelectedRating(initialRating);
      setHoverRating(0);
      setError("");
    }
  }, [isOpen, initialRating]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedRating <= 0) {
      setError("Please select a rating score between 1 and 10.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onRate(selectedRating);
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to submit rating. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const activeRating = hoverRating || selectedRating;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-full max-w-md p-6">
        <DialogHeader className="space-y-1.5 text-center sm:text-center">
          <DialogTitle className="text-xl font-bold tracking-tight text-foreground text-center">
            Rate this title
          </DialogTitle>
          <DialogDescription className="line-clamp-1 max-w-sm mx-auto text-center text-sm font-medium text-muted-foreground">
            {title}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p
            role="alert"
            className="rounded-lg bg-destructive/10 px-3 py-2 text-center text-sm font-medium text-destructive"
          >
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col">
          {/* Active Score Display */}
          <div className="my-3 flex flex-col items-center justify-center rounded-xl border border-border/60 bg-muted/40 p-4 transition-all">
            <div className="flex items-baseline gap-1.5">
              <span className="text-4xl font-extrabold tracking-tight text-yellow-400">
                {activeRating > 0 ? activeRating : "—"}
              </span>
              <span className="text-base font-semibold text-muted-foreground">/ 10</span>
            </div>
            <p className="mt-1 text-xs font-medium text-muted-foreground" aria-live="polite">
              {activeRating > 0
                ? RATING_DESCRIPTIONS[activeRating] || "Your score"
                : "Select a star to choose your rating"}
            </p>
          </div>

          {/* 10-Star Bar */}
          <div
            className="my-2 flex w-full max-w-full items-center justify-between sm:justify-center gap-0.5 sm:gap-1.5 py-2 px-1"
            role="radiogroup"
            aria-label="Rating out of 10"
          >
            {Array.from({ length: 10 }).map((_, i) => {
              const starVal = i + 1;
              const isFilled = activeRating >= starVal;
              return (
                <button
                  key={starVal}
                  type="button"
                  role="radio"
                  aria-checked={selectedRating === starVal}
                  onClick={() => setSelectedRating(starVal)}
                  onMouseEnter={() => setHoverRating(starVal)}
                  onMouseLeave={() => setHoverRating(0)}
                  className="group shrink-0 rounded-md p-0.5 sm:p-1 transition-all duration-150 hover:scale-110 sm:hover:scale-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={`Rate ${starVal} out of 10 — ${RATING_DESCRIPTIONS[starVal]}`}
                >
                  <Star
                    className={cn(
                      "w-5 h-5 sm:w-6 sm:h-6 transition-colors duration-150 shrink-0",
                      isFilled
                        ? "text-yellow-400 drop-shadow-[0_0_6px_rgba(250,204,21,0.5)]"
                        : "text-muted-foreground/35 group-hover:text-yellow-400/60",
                    )}
                    fill={isFilled ? "currentColor" : "none"}
                  />
                </button>
              );
            })}
          </div>

          {selectedRating > 0 && (
            <div className="flex justify-center mt-1">
              <button
                type="button"
                onClick={() => {
                  setSelectedRating(0);
                  setHoverRating(0);
                }}
                className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
              >
                Clear selection
              </button>
            </div>
          )}

          <DialogFooter className="mt-6 flex flex-row items-center justify-end gap-3 pt-4 border-t border-border/50 sm:justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
              className="min-w-[90px]"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="brand"
              disabled={submitting || selectedRating <= 0}
              className="min-w-[120px]"
            >
              {submitting ? "Submitting…" : "Save Rating"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
