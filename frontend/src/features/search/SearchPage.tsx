import { getRouteApi } from "@tanstack/react-router";
import { Search as SearchIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useDebounce } from "@/hooks/useDebounce";
import { useSearch } from "@/hooks/useMovies";
import { MovieGrid } from "@/components/movie/MovieGrid";
import {
  GENRE_OPTIONS,
  LANGUAGE_OPTIONS,
  PLATFORM_OPTIONS,
  YEAR_OPTIONS,
} from "@/utils/genres";
import { EmptyState } from "@/components/common/EmptyState";
import type { SearchSearch } from "@/routes/search";

const routeApi = getRouteApi("/search");

export function SearchPage() {
  const searchParams = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const [q, setQ] = useState(searchParams.q ?? "");
  const debounced = useDebounce(q, 300);

  useEffect(() => {
    navigate({
      to: ".",
      search: (prev: SearchSearch) => ({ ...prev, q: debounced || undefined }),
      replace: true,
    });
  }, [debounced, navigate]);

  const filters = {
    q: debounced,
    genre: searchParams.genre,
    language: searchParams.language,
    platform: searchParams.platform,
    year: searchParams.year,
    sort: searchParams.sort,
  };
  const { data, isLoading, isError, refetch } = useSearch(filters);

  const update = (patch: Partial<SearchSearch>) =>
    navigate({
      to: ".",
      search: (prev: SearchSearch) => ({ ...prev, ...patch }),
    });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search movies, actors, directors..."
            className="w-full rounded-2xl border border-white/10 bg-white/5 py-4 pl-12 pr-4 text-lg focus:outline-none focus:ring-2 focus:ring-primary/60"
          />
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <FilterSelect
          value={searchParams.genre ?? ""}
          placeholder="Genre"
          options={GENRE_OPTIONS}
          onChange={(v) => update({ genre: v || undefined })}
        />
        <FilterSelect
          value={searchParams.language ?? ""}
          placeholder="Language"
          options={LANGUAGE_OPTIONS}
          onChange={(v) => update({ language: v || undefined })}
        />
        <FilterSelect
          value={searchParams.platform ?? ""}
          placeholder="Platform"
          options={PLATFORM_OPTIONS}
          onChange={(v) => update({ platform: v || undefined })}
        />
        <FilterSelect
          value={searchParams.year ?? ""}
          placeholder="Year"
          options={YEAR_OPTIONS}
          onChange={(v) => update({ year: v || undefined })}
        />
        <FilterSelect
          value={searchParams.sort ?? ""}
          placeholder="Sort by"
          options={[
            { label: "Popularity", value: "popularity" },
            { label: "Latest", value: "latest" },
            { label: "IMDb", value: "imdb" },
            { label: "Rabbit Match", value: "rabbit" },
          ]}
          onChange={(v) =>
            update({ sort: (v as SearchSearch["sort"]) || undefined })
          }
        />
      </div>

      {!debounced ? (
        <EmptyState
          title="Start typing to search"
          description="Find movies by title, actor, or director."
          icon={<SearchIcon className="h-10 w-10" />}
        />
      ) : (
        <MovieGrid
          movies={data?.results}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
          columns={4}
        />
      )}
    </div>
  );
}

type Opt = string | { label: string; value: string };
function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Opt[];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/60"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => {
        const label = typeof o === "string" ? o : o.label;
        const val = typeof o === "string" ? o : o.value;
        return (
          <option key={val} value={val}>
            {label}
          </option>
        );
      })}
    </select>
  );
}
