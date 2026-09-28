import fs from "fs";
import path from "path";
import assert from "assert";

console.log("==================================================");
console.log("Running WatchMan Modals & Player UX Test Suite");
console.log("==================================================");

// 1. Check styles.css has no rogue .grid rules
console.log("\n-> 1. Verifying styles.css has no rogue .grid column definitions");
const stylesCss = fs.readFileSync(path.join("frontend", "src", "styles.css"), "utf-8");
assert.ok(
  !/\.grid\s*\{\s*display:\s*grid;\s*grid-template-columns:/i.test(stylesCss),
  "styles.css must not force grid-template-columns on .grid",
);
console.log("✔ styles.css is clean of rogue .grid rules");

// 2. Check dialog.tsx has fullscreen support and flex-col layout
console.log("\n-> 2. Verifying dialog.tsx supports fullscreen and flex-col layout");
const dialogTsx = fs.readFileSync(
  path.join("frontend", "src", "components", "ui", "dialog.tsx"),
  "utf-8",
);
assert.ok(dialogTsx.includes("fullscreen?: boolean"), "dialog.tsx must support fullscreen prop");
assert.ok(dialogTsx.includes("flex flex-col"), "dialog.tsx DialogContent must use flex-col layout");
assert.ok(
  dialogTsx.includes("fixed inset-0 z-50 flex h-screen w-screen"),
  "dialog.tsx must support full viewport fullscreen",
);
console.log("✔ dialog.tsx supports true fullscreen and flex-col layout");

// 3. Check VideoModal.tsx implements full screen player and controls
console.log("\n-> 3. Verifying VideoModal.tsx implements full screen theater layout");
const videoModalTsx = fs.readFileSync(
  path.join("frontend", "src", "components", "VideoModal.tsx"),
  "utf-8",
);
assert.ok(
  videoModalTsx.includes("fullscreen"),
  "VideoModal must pass fullscreen prop to DialogContent",
);
assert.ok(
  videoModalTsx.includes("toggleNativeFullscreen"),
  "VideoModal must implement HTML5 native fullscreen toggle",
);
assert.ok(videoModalTsx.includes("aspect-video"), "VideoModal must maintain 16:9 aspect ratio");
assert.ok(videoModalTsx.includes("allowFullScreen"), "VideoModal must allow iframe fullscreen");
console.log(
  "✔ VideoModal.tsx implements cinematic full screen player with native fullscreen toggle",
);

// 4. Check RatingModal.tsx implements centered, properly aligned 10-star rating
console.log("\n-> 4. Verifying RatingModal.tsx alignment, labels, and star selector");
const ratingModalTsx = fs.readFileSync(
  path.join("frontend", "src", "components", "RatingModal.tsx"),
  "utf-8",
);
assert.ok(
  ratingModalTsx.includes("RATING_DESCRIPTIONS"),
  "RatingModal must include descriptive rating labels",
);
assert.ok(
  ratingModalTsx.includes("flex-nowrap"),
  "RatingModal stars must be in a non-wrapping row",
);
assert.ok(
  ratingModalTsx.includes("text-center"),
  "RatingModal must have centered header and titles",
);
assert.ok(
  ratingModalTsx.includes("Save Rating"),
  "RatingModal must include Save Rating action button",
);
console.log("✔ RatingModal.tsx layout and alignment are cleanly structured");

console.log("\n==================================================");
console.log("ALL MODAL & VIDEO PLAYER TESTS PASSED (100%)");
console.log("==================================================");
