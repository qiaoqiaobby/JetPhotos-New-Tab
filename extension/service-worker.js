// service-worker.js — Manifest V3 background worker (module).
//
// Deliberately minimal: warm the prefetch cache so the first paint of a new tab
// can come from chrome.storage instead of the network.
//   • onInstalled  → one prefetch pass + register a recurring alarm
//   • alarms       → prefetch every 4 hours
//
// It only fetches metadata JSON (small, CORS-friendly on GitHub Pages) and
// best-effort base64-caches the thumbnail. Image bytes may fail to cache if the
// CDN doesn't send CORS headers — that's fine, the new-tab page still renders by
// pointing background-image straight at the CDN URL.

import CONFIG from "./config.js";
import PHOTO_IDS from "./photo-ids.js";
import { addCached, clearExpired, blobToBase64, cacheCount } from "./cache.js";

const ALARM = "prefetch-photos";

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM, { delayInMinutes: 1, periodInMinutes: 240 });
  prefetch().catch(() => {});
});

chrome.runtime.onStartup?.addListener(() => {
  prefetch().catch(() => {});
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM) prefetch().catch(() => {});
});

function pickRandomIds(n) {
  if (!Array.isArray(PHOTO_IDS) || PHOTO_IDS.length === 0) return [];
  const pool = [...PHOTO_IDS];
  const picks = [];
  while (picks.length < n && pool.length) {
    const i = Math.floor(Math.random() * pool.length);
    picks.push(pool.splice(i, 1)[0]);
  }
  return picks;
}

async function fetchJson(url, timeoutMs) {
  const resp = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function prefetch() {
  await clearExpired(CONFIG.CACHE_TTL_MS);
  const have = await cacheCount(CONFIG.CACHE_TTL_MS);
  const need = Math.max(0, CONFIG.CACHE_MAX_ITEMS - have);
  if (need === 0) return;

  const ids = pickRandomIds(Math.min(need, CONFIG.PREFETCH_COUNT));
  for (const id of ids) {
    try {
      const metadata = await fetchJson(
        `${CONFIG.DATA_BASE_URL}/photos/${id}.json`,
        CONFIG.FETCH_TIMEOUT_MS
      );
      let imageDataUrl = null;
      const imgUrl = metadata.thumb_url || metadata.image_url;
      try {
        const imgResp = await fetch(imgUrl, { signal: AbortSignal.timeout(CONFIG.IMAGE_TIMEOUT_MS) });
        if (imgResp.ok) imageDataUrl = await blobToBase64(await imgResp.blob());
      } catch (_) {
        // CORS / network — leave imageDataUrl null; page will use CDN URL directly.
      }
      await addCached(
        { metadata, imageDataUrl, imageUrl: metadata.image_url, cachedAt: Date.now() },
        CONFIG.CACHE_MAX_ITEMS
      );
    } catch (_) {
      // skip this id silently
    }
  }
}
