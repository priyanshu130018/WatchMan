import assert from "node:assert";

// Mock minimal browser environment
class MockClassList {
  constructor() {
    this.classes = new Set();
  }
  add(cls) {
    this.classes.add(cls);
  }
  remove(cls) {
    this.classes.delete(cls);
  }
  contains(cls) {
    return this.classes.has(cls);
  }
}

class MockElement {
  constructor() {
    this.classList = new MockClassList();
    this.style = {};
    this.attributes = new Map();
  }
  setAttribute(k, v) {
    this.attributes.set(k, v);
  }
  getAttribute(k) {
    return this.attributes.get(k);
  }
}

const mockLocalStorage = {
  store: {},
  getItem(k) {
    return this.store[k] ?? null;
  },
  setItem(k, v) {
    this.store[k] = String(v);
  },
  removeItem(k) {
    delete this.store[k];
  },
  clear() {
    this.store = {};
  },
};

globalThis.localStorage = mockLocalStorage;
globalThis.document = {
  documentElement: new MockElement(),
};
globalThis.window = {
  localStorage: mockLocalStorage,
  matchMedia: (query) => ({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }),
};

console.log("=== Testing Theme Store & Anti-FOUC Logic ===");

// 1. Test anti-FOUC script function
function runAntiFOUC(storageKey = "watchman-theme") {
  try {
    var stored = localStorage.getItem(storageKey);
    var theme = "dark";
    if (stored) {
      try {
        var parsed = JSON.parse(stored);
        theme = parsed.state?.theme || parsed.theme || stored;
      } catch (e) {
        theme = stored;
      }
    }
    var resolved = theme;
    if (theme === "system" || !theme) {
      resolved =
        window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark";
    }
    var root = document.documentElement;
    if (resolved === "dark") {
      root.classList.add("dark");
      root.classList.remove("light");
      root.style.colorScheme = "dark";
    } else {
      root.classList.add("light");
      root.classList.remove("dark");
      root.style.colorScheme = "light";
    }
    root.setAttribute("data-theme", resolved);
  } catch (e) {}
}

// Subtest A: default behavior (empty localStorage)
localStorage.clear();
document.documentElement.classList.classes.clear();
runAntiFOUC();
assert.strictEqual(
  document.documentElement.classList.contains("dark"),
  true,
  "Default theme should be dark",
);
assert.strictEqual(document.documentElement.classList.contains("light"), false);
assert.strictEqual(document.documentElement.style.colorScheme, "dark");
assert.strictEqual(document.documentElement.getAttribute("data-theme"), "dark");
console.log("✔ Anti-FOUC default dark initialization passed");

// Subtest B: stored light theme
localStorage.setItem("watchman-theme", JSON.stringify({ state: { theme: "light" } }));
runAntiFOUC();
assert.strictEqual(
  document.documentElement.classList.contains("light"),
  true,
  "Stored light should initialize light",
);
assert.strictEqual(document.documentElement.classList.contains("dark"), false);
assert.strictEqual(document.documentElement.style.colorScheme, "light");
assert.strictEqual(document.documentElement.getAttribute("data-theme"), "light");
console.log("✔ Anti-FOUC stored light initialization passed");

// Subtest C: stored system theme with prefers-color-scheme: light
window.matchMedia = (q) => ({
  matches: q.includes("light"),
  addEventListener: () => {},
  removeEventListener: () => {},
});
localStorage.setItem("watchman-theme", JSON.stringify({ state: { theme: "system" } }));
runAntiFOUC();
assert.strictEqual(
  document.documentElement.classList.contains("light"),
  true,
  "System theme with light preference",
);
console.log("✔ Anti-FOUC system light preference passed");

// Subtest D: Import real useThemeStore and test state transitions
const { useThemeStore } = await import("./src/store/themeStore.ts");

// Reset to dark
useThemeStore.getState().setTheme("dark");
assert.strictEqual(useThemeStore.getState().theme, "dark");
assert.strictEqual(useThemeStore.getState().resolvedTheme, "dark");
assert.strictEqual(document.documentElement.classList.contains("dark"), true);
assert.strictEqual(document.documentElement.getAttribute("data-theme"), "dark");

// Toggle to light
useThemeStore.getState().toggleTheme();
assert.strictEqual(useThemeStore.getState().theme, "light");
assert.strictEqual(useThemeStore.getState().resolvedTheme, "light");
assert.strictEqual(document.documentElement.classList.contains("light"), true);
assert.strictEqual(document.documentElement.classList.contains("dark"), false);
assert.strictEqual(document.documentElement.getAttribute("data-theme"), "light");

// Toggle back to dark
useThemeStore.getState().toggleTheme();
assert.strictEqual(useThemeStore.getState().theme, "dark");
assert.strictEqual(useThemeStore.getState().resolvedTheme, "dark");
assert.strictEqual(document.documentElement.classList.contains("dark"), true);
console.log("✔ ThemeStore state transitions and toggleTheme passed");

// Verify localStorage persistence
const persisted = JSON.parse(localStorage.getItem("watchman-theme"));
assert.strictEqual(persisted.state.theme, "dark");
console.log("✔ Theme persistence in localStorage verified");

console.log("\nALL THEME INTEGRATION TESTS PASSED!");
