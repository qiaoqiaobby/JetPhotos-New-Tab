// cache.js — storage layer for the extension.
//
// Wraps chrome.storage.local (with a localStorage fallback so newtab.html can be
// opened outside an extension for quick UI checks) and provides:
//   • a small prefetch cache queue (metadata + optional base64 image)
//   • recent-history tracking (anti-repeat)
//   • favorites
//
// Safe to import from both the new-tab page and the (module) service worker:
// it uses no DOM and no FileReader.

const CACHE_KEY = "photo_cache_v1";
const HISTORY_KEY = "history_v1";
const FAVORITES_KEY = "favorites_v1";

// ── storage abstraction ──────────────────────────────────────────────
const hasChromeStorage =
  typeof chrome !== "undefined" && chrome.storage && chrome.storage.local;

function _localGet(keys) {
  const out = {};
  const names = Array.isArray(keys) ? keys : keys == null ? null : [keys];
  try {
    if (names === null) {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        out[k] = JSON.parse(localStorage.getItem(k));
      }
    } else {
      for (const k of names) {
        const v = localStorage.getItem(k);
        if (v !== null) out[k] = JSON.parse(v);
      }
    }
  } catch (_) { /* ignore */ }
  return out;
}

export const store = {
  async get(keys) {
    if (hasChromeStorage) return chrome.storage.local.get(keys);
    return _localGet(keys);
  },
  async set(obj) {
    if (hasChromeStorage) return chrome.storage.local.set(obj);
    for (const [k, v] of Object.entries(obj)) localStorage.setItem(k, JSON.stringify(v));
  },
  async remove(keys) {
    if (hasChromeStorage) return chrome.storage.local.remove(keys);
    for (const k of (Array.isArray(keys) ? keys : [keys])) localStorage.removeItem(k);
  },
};

// ── base64 helper (SW-safe: no FileReader) ───────────────────────────
export async function blobToBase64(blob) {
  const buf = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < buf.length; i += chunk) {
    binary += String.fromCharCode.apply(null, buf.subarray(i, i + chunk));
  }
  const b64 = btoa(binary);
  const type = blob.type || "image/jpeg";
  return `data:${type};base64,${b64}`;
}

// ── prefetch cache queue ─────────────────────────────────────────────
// Entry: { metadata, imageDataUrl|null, imageUrl, cachedAt }

async function _readCache() {
  const data = await store.get(CACHE_KEY);
  const arr = data[CACHE_KEY];
  return Array.isArray(arr) ? arr : [];
}

function _isFresh(entry, ttlMs) {
  return entry && typeof entry.cachedAt === "number" && Date.now() - entry.cachedAt < ttlMs;
}

/** Return (and consume) the freshest non-expired cache entry, or null. */
export async function getCached(ttlMs = 24 * 60 * 60 * 1000) {
  const arr = await _readCache();
  const idx = arr.findIndex((e) => _isFresh(e, ttlMs));
  if (idx === -1) return null;
  const [entry] = arr.splice(idx, 1);
  await store.set({ [CACHE_KEY]: arr });
  return entry;
}

/** Peek without consuming (used to know how many fresh entries exist). */
export async function cacheCount(ttlMs = 24 * 60 * 60 * 1000) {
  const arr = await _readCache();
  return arr.filter((e) => _isFresh(e, ttlMs)).length;
}

/** Add one entry, dedup by id, cap to maxItems (drop oldest). */
export async function addCached(entry, maxItems = 5) {
  if (!entry || !entry.metadata || !entry.metadata.id) return;
  let arr = await _readCache();
  arr = arr.filter((e) => e.metadata && e.metadata.id !== entry.metadata.id);
  arr.unshift({ ...entry, cachedAt: entry.cachedAt || Date.now() });
  if (arr.length > maxItems) arr = arr.slice(0, maxItems);
  await store.set({ [CACHE_KEY]: arr });
}

/** Replace the entire cache (matches the documented setCached API). */
export async function setCached(entries) {
  await store.set({ [CACHE_KEY]: Array.isArray(entries) ? entries : [] });
}

/** Drop expired entries. */
export async function clearExpired(ttlMs = 24 * 60 * 60 * 1000) {
  const arr = await _readCache();
  const fresh = arr.filter((e) => _isFresh(e, ttlMs));
  if (fresh.length !== arr.length) await store.set({ [CACHE_KEY]: fresh });
}

// ── recent history (anti-repeat) ─────────────────────────────────────
export async function getHistory() {
  const data = await store.get(HISTORY_KEY);
  return Array.isArray(data[HISTORY_KEY]) ? data[HISTORY_KEY] : [];
}

export async function addToHistory(id, maxSize = 30) {
  let hist = await getHistory();
  hist = hist.filter((x) => x !== id);
  hist.push(id);
  if (hist.length > maxSize) hist = hist.slice(hist.length - maxSize);
  await store.set({ [HISTORY_KEY]: hist });
}

export async function clearHistory() {
  await store.remove(HISTORY_KEY);
}

// ── favorites ────────────────────────────────────────────────────────
export async function getFavorites() {
  const data = await store.get(FAVORITES_KEY);
  return Array.isArray(data[FAVORITES_KEY]) ? data[FAVORITES_KEY] : [];
}

export async function isFavorite(id) {
  return (await getFavorites()).some((f) => f.id === id);
}

/** Toggle a favorite. Pass the full metadata so it can be re-displayed later.
 *  Returns true if now favorited, false if removed. */
export async function toggleFavorite(metadata) {
  if (!metadata || !metadata.id) return false;
  let favs = await getFavorites();
  const exists = favs.some((f) => f.id === metadata.id);
  if (exists) {
    favs = favs.filter((f) => f.id !== metadata.id);
    await store.set({ [FAVORITES_KEY]: favs });
    return false;
  }
  favs.unshift({
    id: metadata.id,
    image_url: metadata.image_url,
    thumb_url: metadata.thumb_url,
    aircraft: metadata.aircraft,
    addedAt: Date.now(),
  });
  await store.set({ [FAVORITES_KEY]: favs });
  return true;
}
