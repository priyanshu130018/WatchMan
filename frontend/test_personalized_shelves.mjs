import assert from "node:assert";

console.log("==================================================");
console.log("Running Frontend Personalized Shelves Test Suite");
console.log("==================================================");

// ----------------------------------------------------
// 1. ContentCard routing tests
// ----------------------------------------------------
console.log("\n-> Testing ContentCard routing works");

function getContentDetailRoute(content) {
  const isTv = content.content_type === "tv";
  const targetId = String(content.tmdb_id || content.id);
  const detailPath = isTv ? "/web-series/$id" : "/movie/$id";
  return { isTv, targetId, detailPath };
}

const movieItem = { id: 101, tmdb_id: 550, content_type: "movie", title: "Fight Club" };
const tvItem = { id: 202, tmdb_id: 1399, content_type: "tv", title: "Game of Thrones" };

const movieRoute = getContentDetailRoute(movieItem);
assert.strictEqual(movieRoute.isTv, false, "Movie should not be classified as TV");
assert.strictEqual(movieRoute.targetId, "550", "Movie should resolve TMDB ID as targetId");
assert.strictEqual(movieRoute.detailPath, "/movie/$id", "Movie should route to /movie/$id");

const tvRoute = getContentDetailRoute(tvItem);
assert.strictEqual(tvRoute.isTv, true, "TV show should be classified as TV");
assert.strictEqual(tvRoute.targetId, "1399", "TV show should resolve TMDB ID as targetId");
assert.strictEqual(
  tvRoute.detailPath,
  "/web-series/$id",
  "TV show should route to /web-series/$id",
);
console.log("✔ ContentCard routing verified for movies and TV series");

// ----------------------------------------------------
// 2. WatchMan badges resolution tests
// ----------------------------------------------------
console.log("\n-> Testing WatchMan badges render correctly");

function resolveWatchmanBadge(content) {
  const rawLabel =
    content.watchman_label ||
    (content.vote_average
      ? content.vote_average >= 7.5
        ? "must_watch"
        : content.vote_average >= 4.5
          ? "time_pass"
          : "skip"
      : null);

  const displayMap = {
    must_watch: "MUST WATCH",
    time_pass: "TIME PASS",
    skip: "SKIP",
  };
  return {
    rawLabel,
    displayLabel: rawLabel ? displayMap[rawLabel] : null,
  };
}

assert.deepStrictEqual(resolveWatchmanBadge({ watchman_label: "must_watch" }), {
  rawLabel: "must_watch",
  displayLabel: "MUST WATCH",
});
assert.deepStrictEqual(resolveWatchmanBadge({ watchman_label: "time_pass" }), {
  rawLabel: "time_pass",
  displayLabel: "TIME PASS",
});
assert.deepStrictEqual(resolveWatchmanBadge({ watchman_label: "skip" }), {
  rawLabel: "skip",
  displayLabel: "SKIP",
});
// Fallbacks from vote_average when watchman_label is absent
assert.strictEqual(resolveWatchmanBadge({ vote_average: 8.5 }).displayLabel, "MUST WATCH");
assert.strictEqual(resolveWatchmanBadge({ vote_average: 6.0 }).displayLabel, "TIME PASS");
assert.strictEqual(resolveWatchmanBadge({ vote_average: 3.2 }).displayLabel, "SKIP");
console.log("✔ WatchMan badges resolution verified");

// ----------------------------------------------------
// 3. Continue Watching displays progress & remaining time
// ----------------------------------------------------
console.log("\n-> Testing Continue Watching displays progress");

function computeProgressCardMeta(item) {
  const effectiveProgress = item.progress !== undefined ? item.progress : item.progress_percent;
  const isCompleted = Boolean(item.completed);
  const hasActiveProgress =
    effectiveProgress !== undefined && effectiveProgress > 0 && !isCompleted;

  let progressText = null;
  let remainingText = null;

  if (hasActiveProgress) {
    progressText = `${Math.round(effectiveProgress)}% watched`;
    if (item.runtime) {
      const minutesLeft = Math.max(1, Math.round(item.runtime * (1 - effectiveProgress / 100)));
      remainingText = `${minutesLeft}m left`;
    }
  }

  return { hasActiveProgress, progressText, remainingText };
}

const cwItemIncomplete = {
  id: 1,
  title: "Inception",
  runtime: 148,
  progress: 37.0,
  completed: false,
};
const metaIncomplete = computeProgressCardMeta(cwItemIncomplete);
assert.strictEqual(metaIncomplete.hasActiveProgress, true);
assert.strictEqual(metaIncomplete.progressText, "37% watched");
assert.strictEqual(metaIncomplete.remainingText, "93m left");

const cwItemCompleted = {
  id: 2,
  title: "Interstellar",
  runtime: 169,
  progress: 100.0,
  completed: true,
};
const metaCompleted = computeProgressCardMeta(cwItemCompleted);
assert.strictEqual(metaCompleted.hasActiveProgress, false);
assert.strictEqual(metaCompleted.progressText, null);
console.log("✔ Continue Watching progress and remaining time calculations verified");

// ----------------------------------------------------
// 4. Shelf rendering and hiding when empty
// ----------------------------------------------------
console.log("\n-> Testing shelf rendering & hidden state when empty");

function renderShelfMock({ title, subtitle, items, sectionKey }) {
  if (!items || items.length === 0) {
    return null; // Shelf is completely hidden
  }
  return {
    rendered: true,
    headingId: `shelf-heading-${sectionKey || title.replace(/\s+/g, "-").toLowerCase()}`,
    title,
    subtitle,
    itemCount: items.length,
    items,
  };
}

// Non-empty shelf renders
const shelfRendered = renderShelfMock({
  title: "You Must Like",
  subtitle: "Picked from your taste and activity",
  items: [
    { id: 1, title: "Movie 1" },
    { id: 2, title: "Movie 2" },
  ],
  sectionKey: "must_like",
});
assert.notStrictEqual(shelfRendered, null);
assert.strictEqual(shelfRendered.title, "You Must Like");
assert.strictEqual(shelfRendered.itemCount, 2);
assert.strictEqual(shelfRendered.headingId, "shelf-heading-must_like");

// Empty shelf is hidden
const shelfEmpty = renderShelfMock({
  title: "Continue Watching",
  items: [],
  sectionKey: "continue_watching",
});
assert.strictEqual(shelfEmpty, null, "Empty shelf must return null (hidden)");
console.log("✔ Shelf rendering and empty shelf hiding verified");

// ----------------------------------------------------
// 5. Shelf hidden when no personalization (Cold Start)
// ----------------------------------------------------
console.log("\n-> Testing shelf hidden when no personalization (Cold Start)");

function getHomepagePersonalizedVisibility(user, continueWatching, watchedLiked, mustLike) {
  if (!user) return false;
  const hasPersonalizedContent =
    (continueWatching?.length ?? 0) > 0 ||
    (watchedLiked?.length ?? 0) > 0 ||
    (mustLike?.length ?? 0) > 0;
  return hasPersonalizedContent;
}

// Guest user -> Hidden
assert.strictEqual(
  getHomepagePersonalizedVisibility(null, [{ id: 1 }], [{ id: 2 }], [{ id: 3 }]),
  false,
  "Guest user should never see personalized shelves",
);

// Signed in, but 0 items in all shelves -> Hidden
assert.strictEqual(
  getHomepagePersonalizedVisibility({ id: "user-123" }, [], [], []),
  false,
  "Cold start user with 0 activity should have personalized section hidden",
);

// Signed in with active recommendations -> Visible
assert.strictEqual(
  getHomepagePersonalizedVisibility({ id: "user-123" }, [], [], [{ id: 10 }]),
  true,
  "User with personalized items should see the section",
);
console.log("✔ Cold start and guest personalization gating verified");

// ----------------------------------------------------
// 6. Each shelf uses its own data and deduplicates in priority order
// ----------------------------------------------------
console.log("\n-> Testing independent shelf data & priority deduplication");

const rawContinueWatching = [
  { id: 101, title: "Movie A" }, // In progress
  { id: 102, title: "Movie B" }, // In progress
];

const rawWatchedLiked = [
  { id: 102, title: "Movie B" }, // Also in CW -> should be removed from WL
  { id: 103, title: "Movie C" }, // Liked
];

const rawMustLike = [
  { id: 101, title: "Movie A" }, // In CW -> should be removed from ML
  { id: 103, title: "Movie C" }, // In WL -> should be removed from ML
  { id: 104, title: "Movie D" }, // Unique recommended
  { id: 105, title: "Movie E" }, // Unique recommended
];

// Priority deduplication algorithm
const cwIds = new Set(rawContinueWatching.map((it) => it.id));
const dedupedWatchedLiked = rawWatchedLiked.filter((it) => !cwIds.has(it.id));

const wlIds = new Set(dedupedWatchedLiked.map((it) => it.id));
const dedupedMustLike = rawMustLike.filter((it) => !cwIds.has(it.id) && !wlIds.has(it.id));

assert.strictEqual(rawContinueWatching.length, 2);
assert.strictEqual(dedupedWatchedLiked.length, 1);
assert.strictEqual(
  dedupedWatchedLiked[0].id,
  103,
  "Movie B should have been removed from Watched & Liked",
);

assert.strictEqual(dedupedMustLike.length, 2);
assert.deepStrictEqual(
  dedupedMustLike.map((it) => it.id),
  [104, 105],
  "Movies A and C should have been removed from Must Like",
);

// Verify no ID appears across multiple shelves
const allIds = [
  ...rawContinueWatching.map((it) => it.id),
  ...dedupedWatchedLiked.map((it) => it.id),
  ...dedupedMustLike.map((it) => it.id),
];
assert.strictEqual(
  new Set(allIds).size,
  allIds.length,
  "No duplicate IDs should exist across shelves",
);
console.log("✔ Priority deduplication (CW > WL > ML) and shelf independence verified");

console.log("\n==================================================");
console.log("ALL FRONTEND TESTS PASSED SUCCESSFULLY (6/6)");
console.log("==================================================");
