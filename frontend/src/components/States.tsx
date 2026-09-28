import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { getApiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({
  icon = (
    <img
      src="/watchman-icon.png"
      alt=""
      className="h-14 w-14 rounded-xl opacity-50"
      width={56}
      height={56}
    />
  ),
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border bg-card/40 px-6 py-14 text-center"
      role="status"
    >
      <div className="text-muted-foreground">{icon}</div>
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
}

export function ErrorState({ title = "Something went wrong", error, onRetry }: ErrorStateProps) {
  const errorMessage = error
    ? getApiErrorMessage(error)
    : "Unable to load content right now. Please try again.";

  return (
    <div
      className="flex flex-col items-center gap-3 rounded-2xl border border-destructive/30 bg-destructive/5 px-6 py-14 text-center"
      role="alert"
    >
      <AlertCircle size={36} className="text-destructive" aria-hidden="true" />
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      <p className="max-w-md text-sm text-muted-foreground">{errorMessage}</p>
      {onRetry && (
        <Button type="button" onClick={onRetry} variant="outline" className="mt-2">
          <RefreshCw size={15} aria-hidden="true" /> Try again
        </Button>
      )}
    </div>
  );
}
