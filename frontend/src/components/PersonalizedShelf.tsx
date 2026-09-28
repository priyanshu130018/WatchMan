import React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { ContentCard } from "./ContentCard";
import { SectionSkeleton } from "./Skeletons";
import { type ContentItem } from "@/types/content";

export interface PersonalizedShelfProps {
  title: string;
  subtitle?: string;
  items?: ContentItem[];
  sectionKey?: string;
  isLoading?: boolean;
  emptyState?: React.ReactNode;
  showTypeBadge?: boolean;
  exploreLink?: string;
  exploreSearch?: Record<string, any>;
  maxItems?: number;
}

export function PersonalizedShelf({
  title,
  subtitle,
  items,
  sectionKey,
  isLoading = false,
  emptyState,
  showTypeBadge = true,
  exploreLink,
  exploreSearch,
  maxItems = 12,
}: PersonalizedShelfProps) {
  if (isLoading) {
    return <SectionSkeleton />;
  }

  if (!items || items.length === 0) {
    return emptyState ? <>{emptyState}</> : null;
  }

  const keySlug = sectionKey || title.replace(/\s+/g, "-").toLowerCase();
  const headingId = `shelf-heading-${keySlug}`;
  const displayedItems = items.slice(0, maxItems);

  return (
    <section className="pt-8" aria-labelledby={headingId} data-shelf={sectionKey}>
      <div className="mb-3.5 flex items-end justify-between gap-4">
        <div>
          {subtitle && (
            <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
              {subtitle}
            </span>
          )}
          <h3
            id={headingId}
            className="mt-0.5 text-xl font-bold tracking-tight text-foreground sm:text-2xl"
          >
            {title}
          </h3>
        </div>
        {exploreLink && (
          <Link
            to={exploreLink}
            search={exploreSearch}
            className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
          >
            View all <ArrowRight size={14} aria-hidden="true" />
          </Link>
        )}
      </div>

      <ul
        className="-mx-1 flex snap-x gap-4 overflow-x-auto px-1 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="region"
        aria-label={title}
      >
        {displayedItems.map((item) => (
          <li
            key={`${item.content_type || "content"}-${item.id || item.tmdb_id}`}
            className="w-[42vw] shrink-0 snap-start sm:w-[30vw] md:w-44 lg:w-48"
          >
            <ContentCard
              content={item}
              showTypeBadge={showTypeBadge}
              progress={item.progress}
              completed={item.completed}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
