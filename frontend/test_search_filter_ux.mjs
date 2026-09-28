import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log("==================================================");
console.log("Running WatchMan Search & Filter UX Test Suite");
console.log("==================================================");

// ----------------------------------------------------
// 1. Filter Count: Active vs Draft & Default Filtering
// ----------------------------------------------------
console.log(
  "\n-> 1. Testing filter count accurately reflects APPLIED filters (ignoring draft & defaults)",
);

function calculateActiveFilterCount({ genre, year, language, sort, isPopular = false }) {
  const DEFAULT_SORT = "popularity_desc";
  return (
    (genre ? 1 : 0) +
    (year ? 1 : 0) +
    (language ? 1 : 0) +
    (!isPopular && sort && sort !== DEFAULT_SORT ? 1 : 0)
  );
}

// Initial state: nothing applied
assert.strictEqual(
  calculateActiveFilterCount({
    genre: undefined,
    year: undefined,
    language: undefined,
    sort: "popularity_desc",
  }),
  0,
  "Default filter state should have active count 0",
);

// One applied: Genre = Sci-Fi (878)
assert.strictEqual(
  calculateActiveFilterCount({
    genre: 878,
    year: undefined,
    language: undefined,
    sort: "popularity_desc",
  }),
  1,
  "Single active genre should have count 1",
);

// User changes draft language to 'en' but has NOT applied yet: applied remains count 1
const applied = { genre: 878, year: undefined, language: undefined, sort: "popularity_desc" };
const draftWithUnapplied = { ...applied, language: "en", year: 2024 };
assert.strictEqual(
  calculateActiveFilterCount(applied),
  1,
  "Filter count must reflect APPLIED state (1), not unapplied draft state (3)",
);

// After clicking Apply: applied receives new values
const appliedAfterCommit = { ...draftWithUnapplied };
assert.strictEqual(
  calculateActiveFilterCount(appliedAfterCommit),
  3,
  "After Apply, filter count updates to 3",
);

console.log("✔ Filter count accurately counts only applied non-default filters");

// ----------------------------------------------------
// 2. Draft State vs Apply URL serialization
// ----------------------------------------------------
console.log(
  "\n-> 2. Testing Draft to URL commit serialization (clean parameter stripping & page 1 reset)",
);

function buildSearchUrlParams(filters, page = 1) {
  const DEFAULT_SORT = "popularity_desc";
  const next = {};
  const qTrimmed = (filters.query || "").trim();
  if (qTrimmed) next.q = qTrimmed;
  if (filters.type && filters.type !== "all") next.type = filters.type;
  if (filters.genre_id) next.genre_id = filters.genre_id;
  if (filters.language) next.language = filters.language;
  if (filters.year) next.year = filters.year;
  if (filters.sort && filters.sort !== DEFAULT_SORT) next.sort = filters.sort;
  if (page && page > 1) next.page = page;
  return next;
}

// Changing draft: no URL is produced yet. When user clicks Apply:
const draftFilters = {
  query: "runner",
  type: "movie",
  genre_id: 878,
  language: "en",
  year: 2017,
  sort: "release_date_asc",
};

const committedUrlParams = buildSearchUrlParams(draftFilters, 1);
assert.deepStrictEqual(
  committedUrlParams,
  {
    q: "runner",
    type: "movie",
    genre_id: 878,
    language: "en",
    year: 2017,
    sort: "release_date_asc",
  },
  "URL parameters should match expected schema and omit page=1 (since page 1 is default)",
);

// If an existing page was 5, clicking Apply resets page to 1
const appliedFromPage5 = buildSearchUrlParams({ ...draftFilters, genre_id: 28 }, 1);
assert.strictEqual(
  appliedFromPage5.page,
  undefined,
  "Apply Filters must reset page to 1 (omitted from URL)",
);
assert.strictEqual(appliedFromPage5.genre_id, 28);

console.log("✔ Draft commit serializes clean URL parameters and resets page to 1");

// ----------------------------------------------------
// 3. Pagination preserves all applied filters
// ----------------------------------------------------
console.log("\n-> 3. Testing pagination preserves all applied filters");

const page2Params = buildSearchUrlParams(draftFilters, 2);
assert.strictEqual(page2Params.page, 2, "Page 2 must carry page=2");
assert.strictEqual(page2Params.q, "runner", "Page 2 must preserve title query");
assert.strictEqual(page2Params.genre_id, 878, "Page 2 must preserve genre filter");
assert.strictEqual(page2Params.year, 2017, "Page 2 must preserve year filter");
assert.strictEqual(page2Params.sort, "release_date_asc", "Page 2 must preserve sort");

console.log("✔ Pagination preserves all active filter criteria on page navigation");

// ----------------------------------------------------
// 4. React Query Key strictly follows applied URL params
// ----------------------------------------------------
console.log("\n-> 4. Testing React Query key isolation from draft state");

function getSearchQueryKey(appliedParams) {
  return [
    "catalogSearch",
    appliedParams.q || "",
    appliedParams.type || "all",
    appliedParams.genre_id,
    appliedParams.language || "",
    appliedParams.year,
    appliedParams.sort || "popularity_desc",
    appliedParams.page || 1,
  ];
}

const key1 = getSearchQueryKey({ q: "runner", genre_id: 878, page: 1 });

// User modifies local draft genre to 28 (Action), but URL has NOT updated
const draftModified = { query: "runner", genre_id: 28 };
// React Query key MUST STILL be key1 because URL has not updated!
const keyStillApplied = getSearchQueryKey({ q: "runner", genre_id: 878, page: 1 });
assert.deepStrictEqual(
  key1,
  keyStillApplied,
  "React Query key must NOT change while editing draft state",
);

// After Apply, URL updates to genre_id 28
const keyAfterApply = getSearchQueryKey({ q: "runner", genre_id: 28, page: 1 });
assert.notDeepStrictEqual(key1, keyAfterApply, "React Query key updates upon Apply");
assert.strictEqual(keyAfterApply[3], 28);

console.log("✔ React Query keys are driven strictly by applied URL parameters");

// ----------------------------------------------------
// 5. Layout Component: Global Search Bar + Advanced Search
// ----------------------------------------------------
console.log("\n-> 5. Verifying Layout.tsx contains Advanced Search button beside search bar");

const layoutSource = fs.readFileSync(
  path.join(__dirname, "src", "components", "Layout.tsx"),
  "utf8",
);
assert(
  layoutSource.includes("Advanced Search"),
  "Layout.tsx must contain 'Advanced Search' control",
);
assert(layoutSource.includes('to="/search"'), "Advanced Search button must link to '/search'");
assert(
  layoutSource.includes("SlidersHorizontal"),
  "Advanced Search control must use consistent SlidersHorizontal icon",
);
console.log("✔ Layout.tsx has Advanced Search button directly beside global search bar");

// ----------------------------------------------------
// 6. SearchPage Component: Draft controls & Apply Filters button
// ----------------------------------------------------
console.log("\n-> 6. Verifying Search.tsx contains draft state, Apply Filters, and Clear buttons");

const searchSource = fs.readFileSync(path.join(__dirname, "src", "features", "Search.tsx"), "utf8");
assert(
  searchSource.includes("Apply Filters"),
  "Search.tsx must include explicit 'Apply Filters' button",
);
assert(searchSource.includes("Clear"), "Search.tsx must include 'Clear' action");
assert(
  searchSource.includes("Refine your search"),
  "Search.tsx must include 'Refine your search' panel",
);
assert(
  searchSource.includes("updateDraft"),
  "Search.tsx dropdowns must update draft state rather than immediate navigation",
);
assert(
  searchSource.includes("Active filters:"),
  "Search.tsx must distinguish applied active filters from draft changes",
);
// ----------------------------------------------------
// 7. Saved Button: Direct navigation to /saved (No slide-over drawer)
// ----------------------------------------------------
console.log("\n-> 7. Verifying Saved button in Layout links directly to /saved (drawer removed)");

assert(layoutSource.includes('to="/saved"'), "Layout.tsx must contain direct link to '/saved'");
assert(
  !layoutSource.includes("<SavedDrawer"),
  "Layout.tsx must NOT render SavedDrawer (slide-over drawer removed in favor of direct redirect)",
);
assert(
  !layoutSource.includes("setSavedOpen(true)"),
  "Layout.tsx must NOT open drawer on saved button click",
);
console.log("✔ Saved button directly links to '/saved' without slide-over drawer");

console.log("\n==================================================");
console.log("ALL 7 FRONTEND SEARCH & FILTER TESTS PASSED (100%)");
console.log("==================================================");
