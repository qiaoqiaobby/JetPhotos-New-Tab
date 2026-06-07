// test.js — Phase 0 CDN load probe (CSP forbids inline script, so this is external).

// Placeholder examples in the documented JetPhotos CDN shape. They WILL fail until
// replaced with real URLs (copy from a photo page's og:image / "Copy image address").
const DEFAULTS = [
  "https://cdn.jetphotos.com/full/6/123456_1700000000.jpg",
  "https://cdn.jetphotos.com/full/2/654321_1699999999.jpg",
  "https://cdn.jetphotos.com/400/6/123456_1700000000.jpg",
  "https://cdn.jetphotos.com/400/2/654321_1699999999.jpg",
  "https://cdn.jetphotos.com/200/6/123456_1700000000.jpg",
];

const results = document.getElementById("results");
const gallery = document.getElementById("gallery");

function sizeHint(url) {
  const m = url.match(/cdn\.jetphotos\.com\/(full|\d+)\//i);
  return m ? m[1] : "?";
}

function probe(url, i) {
  const row = document.createElement("tr");
  row.innerHTML =
    `<td>${i + 1}</td><td class="url">${url}</td><td>${sizeHint(url)}</td>` +
    `<td class="pending">loading…</td><td>—</td><td>—</td>`;
  results.appendChild(row);
  const statusCell = row.children[3];
  const dimCell = row.children[4];
  const msCell = row.children[5];

  const start = performance.now();
  const img = new Image();
  let done = false;
  const timeout = setTimeout(() => finish(false, "timeout"), 12000);

  function finish(ok, note) {
    if (done) return;
    done = true;
    clearTimeout(timeout);
    const ms = Math.round(performance.now() - start);
    statusCell.textContent = ok ? "OK" : `FAIL${note ? " (" + note + ")" : ""}`;
    statusCell.className = ok ? "ok" : "fail";
    dimCell.textContent = ok ? `${img.naturalWidth}×${img.naturalHeight}` : "—";
    msCell.textContent = ms;
    if (ok) {
      const fig = document.createElement("figure");
      const im = document.createElement("img");
      im.src = url;
      const cap = document.createElement("figcaption");
      cap.textContent = `${sizeHint(url)} · ${img.naturalWidth}×${img.naturalHeight}`;
      fig.appendChild(im);
      fig.appendChild(cap);
      gallery.appendChild(fig);
    }
  }

  img.onload = () => finish(img.naturalWidth > 0, "");
  img.onerror = () => finish(false, "blocked/404");
  img.src = url;
}

function runTests(urls) {
  results.innerHTML = "";
  gallery.innerHTML = "";
  urls.forEach(probe);
}

function currentUrls() {
  return document.getElementById("urls").value
    .split("\n").map((s) => s.trim()).filter(Boolean);
}

document.getElementById("run").addEventListener("click", () => runTests(currentUrls()));

document.getElementById("urls").value = DEFAULTS.join("\n");
runTests(DEFAULTS);
