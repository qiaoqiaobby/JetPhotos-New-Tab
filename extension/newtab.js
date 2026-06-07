// newtab.js — runtime for the Aviation Gallery new tab.
//
// Flow (mirrors Google Earth View):
//   init → showPlaceholder → try cache → else online (pick id → fetch meta →
//   load image with full→thumb→fallback degrade → render+crossfade) → prefetch
//
// ── Config ───────────────────────────────────────────────────────────
//   PROD: ./config.js   DEV (local data server): ./config.dev.js
//   To test locally, switch the import below to './config.dev.js' and run
//   scripts/serve-data.sh. Switch back to './config.js' before packaging.
import CONFIG from "./config.js";
// import CONFIG from "./config.dev.js"; // ← uncomment for local development
import PHOTO_IDS from "./photo-ids.js";
import {
  getCached, addCached, clearExpired, blobToBase64,
  getHistory, addToHistory, clearHistory,
  toggleFavorite, isFavorite,
} from "./cache.js";

const PLACEHOLDER = "assets/placeholder.png";

// ── DOM ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const layers = { a: $("layer-a"), b: $("layer-b") };
const loadingEl = $("loading-indicator");
const infoBar = $("info-bar");
const toastEl = $("toast");
const hintEl = $("hint");

// ── State ────────────────────────────────────────────────────────────
let activeLayer = "a";
let currentMetadata = null;
let currentImageUrl = null;
let isLoading = false;
let infoTimer = null;
let loadingTimer = null;

// Session back/forward stack (in-memory; ← / → navigate it).
const sessionStack = [];
let sessionPos = -1;

// ── Boot ─────────────────────────────────────────────────────────────
init();

async function init() {
  wireEvents();
  showPlaceholder();
  flashHint();

  if (!Array.isArray(PHOTO_IDS) || PHOTO_IDS.length === 0) {
    showFallback("No photos configured. Run scripts/sync-photo-ids.sh.");
    return;
  }

  try { await clearExpired(CONFIG.CACHE_TTL_MS); } catch (_) {}

  // 1) Try a prefetched cache entry for an instant first paint.
  let rendered = false;
  try {
    const entry = await getCached(CONFIG.CACHE_TTL_MS);
    if (entry && entry.metadata) {
      await renderFromCache(entry);
      rendered = true;
    }
  } catch (_) {}

  // 2) Otherwise go online.
  if (!rendered) await onlineFlow();

  // 3) Top up the background cache.
  prefetchNext(CONFIG.PREFETCH_COUNT).catch(() => {});
}

// ── Core flows ───────────────────────────────────────────────────────
async function onlineFlow() {
  beginLoading();
  const id = await pickRandomId();
  const metadata = await fetchMetadata(id);
  if (!metadata) {
    showFallback("Couldn't reach the photo library. Check your connection or DATA_BASE_URL.");
    return;
  }
  await loadAndRender(metadata);
}

async function renderFromCache(entry) {
  const metadata = entry.metadata;
  // A base64 data URL is guaranteed-good; render it directly. Otherwise validate.
  if (entry.imageDataUrl) {
    renderPhoto(metadata, entry.imageDataUrl);
    pushSession(metadata, entry.imageDataUrl);
  } else {
    await loadAndRender(metadata, entry.imageUrl);
  }
}

async function loadAndRender(metadata, preferUrl) {
  beginLoading();
  const url = await loadImage(metadata, preferUrl);
  if (url) {
    renderPhoto(metadata, url);
    pushSession(metadata, url);
  } else {
    // Metadata is good but every CDN size failed — show placeholder + info.
    renderPhoto(metadata, PLACEHOLDER);
    pushSession(metadata, PLACEHOLDER);
    toast("Image unavailable — showing details only");
  }
}

// ── Selection ────────────────────────────────────────────────────────
async function pickRandomId() {
  const history = await getHistory();
  let available = PHOTO_IDS.filter((id) => !history.includes(id));
  if (available.length === 0) {
    await clearHistory();
    available = [...PHOTO_IDS];
  }
  const id = available[Math.floor(Math.random() * available.length)];
  await addToHistory(id, CONFIG.HISTORY_SIZE);
  return id;
}

// ── Metadata fetch ───────────────────────────────────────────────────
async function fetchMetadata(photoId) {
  try {
    const url = `${CONFIG.DATA_BASE_URL}/photos/${photoId}.json`;
    const resp = await fetch(url, { signal: AbortSignal.timeout(CONFIG.FETCH_TIMEOUT_MS) });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    console.warn(`metadata load failed [${photoId}]:`, err.message || err);
    return null;
  }
}

// ── Image loading with multi-size degrade ────────────────────────────
async function loadImage(metadata, preferUrl) {
  const candidates = [
    preferUrl,
    metadata.image_url,
    metadata.thumb_url,
    metadata.fallback_url,
  ].filter((u, i, arr) => u && arr.indexOf(u) === i);

  for (const url of candidates) {
    if (await canLoad(url, CONFIG.IMAGE_TIMEOUT_MS)) return url;
  }
  return null;
}

function canLoad(url, timeoutMs) {
  return new Promise((resolve) => {
    const img = new Image();
    let done = false;
    const finish = (ok) => { if (!done) { done = true; clearTimeout(t); resolve(ok); } };
    const t = setTimeout(() => finish(false), timeoutMs);
    img.onload = () => finish(img.naturalWidth > 0);
    img.onerror = () => finish(false);
    img.decoding = "async";
    img.src = url;
  });
}

// ── Rendering ────────────────────────────────────────────────────────
function renderPhoto(metadata, imageUrl) {
  const next = activeLayer === "a" ? "b" : "a";
  const nextEl = layers[next];
  const prevEl = layers[activeLayer];

  nextEl.style.backgroundImage = `url("${cssUrl(imageUrl)}")`;
  // force reflow so the opacity transition runs
  void nextEl.offsetWidth;
  nextEl.classList.add("active");
  prevEl.classList.remove("active");
  activeLayer = next;

  currentMetadata = metadata;
  currentImageUrl = imageUrl;
  endLoading();
  updateInfoBar(metadata);
  scheduleInfoDim();
  refreshFavButton();
}

function cssUrl(u) {
  return String(u).replace(/["\\\n\r]/g, encodeURIComponent);
}

function updateInfoBar(m) {
  const ac = m.aircraft || {};
  const ph = m.photographer || {};
  const loc = m.location || {};

  setText("aircraft-type", ac.type || "Unknown aircraft");
  setText("airline", ac.airline || "");
  setText("registration", ac.registration || "");

  const photographerEl = $("photographer");
  photographerEl.textContent = ph.name || "Unknown photographer";
  if (ph.profile_url) {
    photographerEl.href = ph.profile_url;
    photographerEl.removeAttribute("aria-disabled");
  } else {
    photographerEl.removeAttribute("href");
    photographerEl.setAttribute("aria-disabled", "true");
  }

  const locStr = loc.airport
    ? loc.airport + (loc.iata ? ` (${loc.iata})` : "")
    : (loc.country || "");
  setText("location", locStr);

  const view = $("view-original");
  view.href = m.jetphotos_url || `https://www.jetphotos.com/photo/${m.id}`;

  // Separator visibility
  const mainSeps = infoBar.querySelectorAll(".info-main .separator");
  if (mainSeps[0]) mainSeps[0].classList.toggle("hide", !ac.airline);
  if (mainSeps[1]) mainSeps[1].classList.toggle("hide", !ac.registration);
  const secSep = infoBar.querySelector(".info-secondary .separator");
  if (secSep) secSep.classList.toggle("hide", !locStr);

  setInfoState("visible");
}

function setText(id, value) { $(id).textContent = value || ""; }

// ── Prefetch ─────────────────────────────────────────────────────────
async function prefetchNext(count) {
  await clearExpired(CONFIG.CACHE_TTL_MS);
  const history = await getHistory();
  const pool = PHOTO_IDS.filter((id) => !history.includes(id));
  const source = pool.length >= count ? pool : PHOTO_IDS;

  const picked = new Set();
  while (picked.size < Math.min(count, source.length)) {
    picked.add(source[Math.floor(Math.random() * source.length)]);
  }

  for (const id of picked) {
    try {
      const metadata = await fetchMetadata(id);
      if (!metadata) continue;
      // Warm the browser HTTP cache regardless of CORS.
      const warm = new Image();
      warm.src = metadata.thumb_url || metadata.image_url;
      // Best-effort base64 cache (works only if the CDN allows CORS).
      let imageDataUrl = null;
      try {
        const r = await fetch(metadata.thumb_url || metadata.image_url,
          { signal: AbortSignal.timeout(CONFIG.IMAGE_TIMEOUT_MS) });
        if (r.ok) imageDataUrl = await blobToBase64(await r.blob());
      } catch (_) {}
      await addCached(
        { metadata, imageDataUrl, imageUrl: metadata.image_url, cachedAt: Date.now() },
        CONFIG.CACHE_MAX_ITEMS
      );
    } catch (_) {}
  }
}

// ── Session navigation ───────────────────────────────────────────────
function pushSession(metadata, imageUrl) {
  // drop any forward history if we had navigated back
  if (sessionPos < sessionStack.length - 1) sessionStack.splice(sessionPos + 1);
  sessionStack.push({ metadata, imageUrl });
  if (sessionStack.length > 60) sessionStack.shift();
  sessionPos = sessionStack.length - 1;
}

function goPrev() {
  if (sessionPos > 0) {
    sessionPos--;
    const item = sessionStack[sessionPos];
    renderStored(item);
  } else {
    toast("Start of session history");
  }
}

function goNext() {
  if (sessionPos < sessionStack.length - 1) {
    sessionPos++;
    renderStored(sessionStack[sessionPos]);
  } else {
    nextPhoto(); // fetch a fresh one
  }
}

function renderStored(item) {
  // render without modifying the stack
  const next = activeLayer === "a" ? "b" : "a";
  layers[next].style.backgroundImage = `url("${cssUrl(item.imageUrl)}")`;
  void layers[next].offsetWidth;
  layers[next].classList.add("active");
  layers[activeLayer].classList.remove("active");
  activeLayer = next;
  currentMetadata = item.metadata;
  currentImageUrl = item.imageUrl;
  updateInfoBar(item.metadata);
  scheduleInfoDim();
  refreshFavButton();
}

async function nextPhoto() {
  if (isLoading) return;
  // Prefer a prefetched entry for snappiness.
  try {
    const entry = await getCached(CONFIG.CACHE_TTL_MS);
    if (entry && entry.metadata) {
      await renderFromCache(entry);
      prefetchNext(CONFIG.PREFETCH_COUNT).catch(() => {});
      return;
    }
  } catch (_) {}
  await onlineFlow();
  prefetchNext(CONFIG.PREFETCH_COUNT).catch(() => {});
}

// ── Favorites ────────────────────────────────────────────────────────
async function favoriteCurrent() {
  if (!currentMetadata) return;
  const nowFav = await toggleFavorite(currentMetadata);
  $("fav-btn").classList.toggle("faved", nowFav);
  toast(nowFav ? "Added to favorites ♥" : "Removed from favorites");
}

async function refreshFavButton() {
  if (!currentMetadata) return;
  const fav = await isFavorite(currentMetadata.id);
  $("fav-btn").classList.toggle("faved", fav);
}

// ── Info overlay state ───────────────────────────────────────────────
function setInfoState(state) { infoBar.setAttribute("data-state", state); }

function scheduleInfoDim() {
  clearTimeout(infoTimer);
  setInfoState("visible");
  infoTimer = setTimeout(() => {
    if (infoBar.getAttribute("data-state") === "visible") setInfoState("dimmed");
  }, 3000);
}

function toggleInfo() {
  const s = infoBar.getAttribute("data-state");
  if (s === "hidden") { setInfoState("visible"); scheduleInfoDim(); }
  else setInfoState("hidden");
}

// ── Placeholder / loading / toast ────────────────────────────────────
function showPlaceholder() {
  layers.a.style.backgroundImage = `url("${PLACEHOLDER}")`;
  layers.a.classList.add("active");
}

function beginLoading() {
  isLoading = true;
  clearTimeout(loadingTimer);
  // only show the spinner if loading is slow, to avoid flicker
  loadingTimer = setTimeout(() => loadingEl.classList.add("show"), 250);
}

function endLoading() {
  isLoading = false;
  clearTimeout(loadingTimer);
  loadingEl.classList.remove("show");
}

function showFallback(message) {
  renderPhoto(currentMetadata || emptyMeta(), PLACEHOLDER);
  endLoading();
  if (message) toast(message, 4200);
}

function emptyMeta() {
  return { id: "", aircraft: {}, photographer: {}, location: {}, jetphotos_url: "https://www.jetphotos.com/" };
}

let toastTimer = null;
function toast(message, ms = 2200) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), ms);
}

function flashHint() {
  hintEl.classList.add("show");
  setTimeout(() => hintEl.classList.remove("show"), 4500);
}

// ── Events ───────────────────────────────────────────────────────────
function wireEvents() {
  $("refresh-btn").addEventListener("click", () => {
    $("refresh-btn").classList.add("spin");
    setTimeout(() => $("refresh-btn").classList.remove("spin"), 500);
    nextPhoto();
  });
  $("fav-btn").addEventListener("click", favoriteCurrent);

  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case " ":
      case "ArrowRight":
        e.preventDefault(); goNext(); break;
      case "ArrowLeft":
        e.preventDefault(); goPrev(); break;
      case "f": case "F":
        favoriteCurrent(); break;
      case "i": case "I":
        toggleInfo(); break;
      case "Escape":
        setInfoState("hidden"); break;
    }
  });

  // Keep info readable while the pointer is near it.
  infoBar.addEventListener("mouseenter", () => { clearTimeout(infoTimer); setInfoState("visible"); });
  infoBar.addEventListener("mouseleave", scheduleInfoDim);
}
