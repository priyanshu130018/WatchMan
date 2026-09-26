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

export interface RatingModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  initialRating?: number;
  onRate: (rating: number) => Promise<void>;
}

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

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Rate this title</DialogTitle>
          <DialogDescription className="line-clamp-1">{title}</DialogDescription>
        </DialogHeader>

        {error && (
          <p
            role="alert"
            className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit}>
          <div
            className="my-2 flex items-center justify-center gap-1.5 py-4"
            role="radiogroup"
            aria-label="Rating out of 10"
          >
            {Array.from({ length: 10 }).map((_, i) => {
              const starVal = i + 1;
              const isFilled = (hoverRating || selectedRating) >= starVal;
              return (
                <button
                  key={starVal}
                  type="button"
                  role="radio"
                  aria-checked={selectedRating === starVal}
                  onClick={() => setSelectedRating(starVal)}
                  onMouseEnter={() => setHoverRating(starVal)}
                  onMouseLeave={() => setHoverRating(0)}
                  className="rounded p-1 text-muted-foreground transition-colors hover:text-yellow-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={`Rate ${starVal} out of 10`}
                >
                  <Star
                    size={24}
                    className={isFilled ? "text-yellow-400" : "text-muted-foreground"}
                    fill={isFilled ? "currentColor" : "none"}
                  />
                </button>
              );
            })}
          </div>

          <div className="mb-2 text-center text-lg font-bold text-yellow-400" aria-live="polite">
            {selectedRating > 0 ? `${selectedRating} / 10` : "Select your score"}
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" variant="brand" disabled={submitting || selectedRating <= 0}>
              {submitting ? "Submitting…" : "Save Rating"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
