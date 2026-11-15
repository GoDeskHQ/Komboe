/* Refresh the downloads cards from /downloads/komboe-downloads.json when present. */
(function () {
  const grid = document.getElementById("downloads-grid");
  if (!grid) return;

  function size(n) {
    if (!n) return "";
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB (" + n.toLocaleString() + " bytes)";
    if (n >= 1024) return (n / 1024).toFixed(1) + " KB (" + n.toLocaleString() + " bytes)";
    return n + " bytes";
  }

  function escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function card(asset, existing) {
    const article = existing || document.createElement("article");
    article.className = "card glass dl";
    article.setAttribute("data-testid", "marketing-download-" + asset.id);
    if (existing && existing.getAttribute("data-os")) {
      article.setAttribute("data-os", existing.getAttribute("data-os"));
    }
    const url = asset.url || "";
    const published = asset.status === "published" && url;
    let body = "<h3>" + escape(asset.name) + "</h3><p>" + escape((asset.platforms || []).join(", ")) + "</p>";
    if (published) {
      body += "<p><strong>" + escape((asset.channel || "release").replace(/-/g, " ")) + "</strong></p>";
      if (asset.version) body += '<div class="fine"><span>Version</span> ' + escape(asset.version) + "</div>";
      if (asset.size) body += '<div class="fine"><span>Size</span> ' + escape(size(asset.size)) + "</div>";
      if (asset.sha256) body += '<div class="fine sha"><span>SHA-256</span> <code>' + escape(asset.sha256) + "</code></div>";
      if (asset.releasedAt) body += '<div class="fine"><span>Released</span> ' + escape(asset.releasedAt) + "</div>";
      body += '<p><a class="btn p" href="' + escape(url) + '">Download ' + escape(asset.filename || "file") + "</a></p>";
      if (asset.install) body += '<p class="fine">' + escape(asset.install) + "</p>";
    } else {
      body += "<p><strong>Not available.</strong> " + escape(asset.reason || "") + "</p>";
      if (asset.install) body += '<p class="fine">' + escape(asset.install) + "</p>";
    }
    if (asset.docsUrl) {
      body += '<p><a href="' + escape(asset.docsUrl) + '" rel="noopener noreferrer" target="_blank">Instructions</a></p>';
    }
    article.innerHTML = body;
    return article;
  }

  const src = new URL("komboe-downloads.json", window.location.href);
  fetch(src)
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((manifest) => {
      if (!manifest || !Array.isArray(manifest.assets)) return;
      const byId = {};
      grid.querySelectorAll("[data-testid^='marketing-download-']").forEach((el) => {
        byId[el.getAttribute("data-testid").slice("marketing-download-".length)] = el;
      });
      manifest.assets.forEach((asset) => {
        const existing = byId[asset.id];
        const next = card(asset, existing);
        if (!existing) grid.appendChild(next);
      });
      const empty = document.querySelector("[data-testid='downloads-manifest-empty']");
      const hasFile = manifest.assets.some((a) => a.status === "published" && a.url);
      if (empty) empty.hidden = hasFile;
    })
    .catch(() => {});
})();
