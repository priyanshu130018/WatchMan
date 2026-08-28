import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { profileService } from "@/services/profile";
import { qk } from "@/hooks/useMovies";
import { useAuthStore } from "@/store/authStore";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/common/Skeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { UserIcon } from "lucide-react";

export function ProfilePage() {
  const isAuthed = Boolean(useAuthStore((s) => s.token));
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: qk.profile,
    queryFn: profileService.get,
    enabled: isAuthed,
  });

  if (!isAuthed) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20">
        <EmptyState
          title="Sign in to view your profile"
          icon={<UserIcon className="h-10 w-10" />}
          action={
            <Link to="/login">
              <Button className="gradient-rabbit border-0">Sign In</Button>
            </Link>
          }
        />
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
        <Skeleton className="h-32 w-full rounded-3xl" />
        <Skeleton className="h-40 w-full rounded-3xl" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <ErrorState onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-8 flex flex-col items-center gap-4 rounded-3xl glass p-8 text-center sm:flex-row sm:text-left">
        <div className="grid h-24 w-24 place-items-center rounded-full gradient-rabbit text-3xl font-black text-white shadow-cinema">
          {data.username?.[0]?.toUpperCase() ?? "U"}
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-black">{data.username}</h1>
          <p className="text-sm text-muted-foreground">{data.email}</p>
        </div>
        <Button variant="secondary">Edit Profile</Button>
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <StatCard label="Favorites" value={data.stats?.favorites ?? 0} />
        <StatCard label="Watched" value={data.stats?.watched ?? 0} />
        <StatCard
          label="Recommendations"
          value={data.stats?.recommendations ?? 0}
        />
      </div>

      <TagSection title="Favorite Genres" items={data.favorite_genres ?? []} />
      <TagSection
        title="Favorite Languages"
        items={data.favorite_languages ?? []}
      />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-card p-5 ring-1 ring-white/5">
      <p className="text-3xl font-black text-gradient-rabbit">{value}</p>
      <p className="text-xs uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
    </div>
  );
}

function TagSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">None yet</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((t) => (
            <span
              key={t}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
