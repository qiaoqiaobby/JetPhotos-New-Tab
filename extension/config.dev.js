// config.dev.js — LOCAL DEVELOPMENT configuration.
//
// Points at the local data server (scripts/serve-data.sh on :8080) and uses
// small/short values so cache + history behavior is easy to observe.
//
// To use: in newtab.js change the config import to './config.dev.js'.
// REMEMBER to switch back to './config.js' before packaging for release
// (scripts/package.sh deliberately does not include this file).

export default {
  DATA_BASE_URL: "http://localhost:8080",
  PREFETCH_COUNT: 2,
  HISTORY_SIZE: 5,          // small, so you hit the "pool exhausted" reset quickly
  FETCH_TIMEOUT_MS: 3000,
  IMAGE_TIMEOUT_MS: 8000,
  CACHE_MAX_ITEMS: 3,
  CACHE_TTL_MS: 60 * 1000,  // 1 minute, so cache expiry is easy to test
};
