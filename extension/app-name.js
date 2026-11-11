(() => {
  if (globalThis.PWACustomizerAppName) return;
  const requests = new Map();
  const clean = value => typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";

  function metadata(doc) {
    const link = doc.querySelector('link[rel~="manifest" i]');
    const fallback = clean(doc.querySelector('meta[name="application-name" i]')?.content) ||
      clean(doc.querySelector('meta[name="apple-mobile-web-app-title" i]')?.content);
    return {
      url: link?.href || "",
      credentials: link?.crossOrigin === "use-credentials" ? "include" : "same-origin",
      fallback,
    };
  }

  async function resolve(doc) {
    const { url, credentials, fallback } = metadata(doc);
    if (!url || !/^https?:/.test(url)) return fallback;
    const key = JSON.stringify([url, credentials]);
    if (!requests.has(key)) {
      requests.set(key, (async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        try {
          // Fetch in the page's origin/CORS context, with the manifest's normal
          // credential policy. No additional host permissions or third-party service.
          const response = await fetch(url, { credentials, signal: controller.signal });
          if (!response.ok) return "";
          const manifest = await response.json();
          return clean(manifest?.short_name) || clean(manifest?.name);
        } catch {
          return "";
        } finally {
          clearTimeout(timeout);
        }
      })());
    }
    return await requests.get(key) || fallback;
  }

  globalThis.PWACustomizerAppName = {
    resolve,
    signature: doc => JSON.stringify(metadata(doc)),
  };
})();
