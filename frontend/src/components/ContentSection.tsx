import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { ContentCard } from "./ContentCard";
import { SectionSkeleton } from "./Skeletons";
import { type ContentItem } from "@/types/content";

export interface ContentSectionProps {
  title: string;
  subtitle?: string;
  items: ContentItem[];
  exploreLink?: string;
  exploreSearch?: Record<string, any>;
  isLoading?: boolean;
  showTypeBadge?: boolean;
  layout?: "row" | "grid";
  maxItems?: number;
}

export function ContentSection({
  title,
  subtitle,
  items,
  exploreLink,
  exploreSearch,
  isLoading = false,
  showTypeBadge = true,
  layout = "row",
  maxItems = 10,
}: ContentSectionProps) {
  if (isLoading) {
    return <SectionSkeleton />;
  }

  if (!items || items.length === 0) {
    return null;
  }

  const headingId = `section-heading-${title.replace(/\s+/g, "-").toLowerCase()}`;
  const displayedItems = items.slice(0, maxItems);

  return (
    <section className="pt-11" aria-labelledby={headingId}>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          {subtitle && (
            <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
              {subtitle}
            </span>
          )}
          <h2 id={headingId} className="mt-1 text-2xl font-semibold tracking-tight">
            {title}
          </h2>
        </div>
        {exploreLink && (
          <Link
            to={exploreLink}
            search={exploreSearch}
            className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
          >
            Explore <ArrowRight size={15} aria-hidden="true" />
          </Link>
        )}
      </div>

      {layout === "row" ? (
        <ul className="-mx-1 flex snap-x gap-4 overflow-x-auto px-1 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {displayedItems.map((item) => (
            <li
              key={`${item.content_type}-${item.id || item.tmdb_id}`}
              className="w-[42vw] shrink-0 snap-start sm:w-[30vw] md:w-44 lg:w-48"
            >
              <ContentCard content={item} showTypeBadge={showTypeBadge} />
            </li>
          ))}
        </ul>
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {displayedItems.map((item) => (
            <li key={`${item.content_type}-${item.id || item.tmdb_id}`}>
              <ContentCard content={item} showTypeBadge={showTypeBadge} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
