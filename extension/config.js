// config.js — PRODUCTION configuration.
//
// ⚠️  Set DATA_BASE_URL to your deployed GitHub Pages data repo before shipping,
//     e.g. "https://octocat.github.io/jetphotos-data".
//     The placeholder below intentionally does NOT resolve.
//
// For LOCAL development against scripts/serve-data.sh, use config.dev.js instead
// (see the import note at the top of newtab.js).

export default {
  // Where the metadata JSON lives (Layer 2). No trailing slash.
  DATA_BASE_URL: "https://YOUR_USERNAME.github.io/jetphotos-data",

  // How many photos to silently prefetch in the background after render.
  PREFETCH_COUNT: 3,

  // Avoid repeats: don't reshow the last N photos until the pool is exhausted.
  HISTORY_SIZE: 30,

  // Network timeouts.
  FETCH_TIMEOUT_MS: 3000,   // metadata JSON fetch
  IMAGE_TIMEOUT_MS: 8000,   // full-screen image load

  // chrome.storage cache.
  CACHE_MAX_ITEMS: 5,
  CACHE_TTL_MS: 24 * 60 * 60 * 1000, // 24h
};
