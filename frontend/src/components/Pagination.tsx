import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
}

export function Pagination({ page, totalPages, onPageChange, disabled = false }: PaginationProps) {
  if (totalPages <= 1) return null;

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const maxVisible = 5;

    if (totalPages <= maxVisible + 2) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push("...");
      const start = Math.max(2, page - 1);
      const end = Math.min(totalPages - 1, page + 1);
      for (let i = start; i <= end; i++) pages.push(i);
      if (page < totalPages - 2) pages.push("...");
      pages.push(totalPages);
    }

    return pages;
  };

  const navBtn =
    "inline-flex h-9 items-center gap-1 rounded-md border border-border bg-secondary px-3 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <nav className="flex flex-wrap items-center justify-center gap-2" aria-label="Pagination">
      <button
        type="button"
        className={navBtn}
        onClick={() => onPageChange(page - 1)}
        disabled={disabled || page <= 1}
        aria-label="Previous page"
      >
        <ChevronLeft size={16} aria-hidden="true" /> Previous
      </button>

      <div className="flex items-center gap-1">
        {getPageNumbers().map((p, idx) =>
          typeof p === "number" ? (
            <button
              key={idx}
              type="button"
              className={cn(
                "inline-flex h-9 min-w-9 items-center justify-center rounded-md px-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
                p === page
                  ? "bg-brand-gradient text-white"
                  : "border border-border bg-secondary text-foreground hover:bg-accent",
              )}
              onClick={() => onPageChange(p)}
              disabled={disabled || p === page}
              aria-label={`Page ${p}`}
              aria-current={p === page ? "page" : undefined}
            >
              {p}
            </button>
          ) : (
            <span key={idx} className="px-1.5 text-muted-foreground" aria-hidden="true">
              …
            </span>
          ),
        )}
      </div>

      <button
        type="button"
        className={navBtn}
        onClick={() => onPageChange(page + 1)}
        disabled={disabled || page >= totalPages}
        aria-label="Next page"
      >
        Next <ChevronRight size={16} aria-hidden="true" />
      </button>
    </nav>
  );
}
