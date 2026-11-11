/* Shared by the popup, isolated content script, and service worker. */
globalThis.PWARecolor = (() => {
  const LIGHT = "#F5F5F5";
  const DARK = "#202124";
  const PREFIX = "site:";

  function sanitizeHex(value) {
    if (typeof value !== "string") return null;
    const hex = value.trim().replace(/^#/, "");
    if (!/^(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex)) return null;
    return "#" + (hex.length === 3 ? [...hex].map(c => c + c).join("") : hex).toUpperCase();
  }

  function originFromUrl(value) {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.origin : null;
    } catch {
      return null;
    }
  }

  function settings(value) {
    return {
      enabled: value?.enabled === true,
      mode: ["light", "dark", "custom"].includes(value?.mode) ? value.mode : "dark",
      color: sanitizeHex(value?.color) || DARK,
      title: sanitizeTitle(value?.title),
      // Preserve custom titles from 1.1, before there was a separate switch.
      titleEnabled: typeof value?.titleEnabled === "boolean" ? value.titleEnabled : !!sanitizeTitle(value?.title),
      titleMode: ["short", "custom"].includes(value?.titleMode) ? value.titleMode :
        (typeof value?.titleEnabled === "boolean" || sanitizeTitle(value?.title) ? "custom" : "short"),
    };
  }

  function sanitizeTitle(value) {
    if (typeof value !== "string") return "";
    return value.replace(/[\u0000-\u001F\u007F-\u009F]/g, " ").replace(/\s+/g, " ").trim().slice(0, 200).trim();
  }

  function isActive(value) {
    const item = settings(value);
    return item.enabled || item.titleEnabled;
  }

  function withTimeout(promise, milliseconds, message) {
    let timer;
    return Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), milliseconds);
    })]).finally(() => clearTimeout(timer));
  }

  function colorFor(value) {
    const item = settings(value);
    return item.mode === "light" ? LIGHT : item.mode === "dark" ? DARK : item.color;
  }

  // Chrome host permissions cover all ports; settings still use the exact origin.
  function patternFor(origin) {
    const url = new URL(origin);
    return `${url.protocol}//${url.hostname}/*`;
  }

  return { PREFIX, sanitizeHex, sanitizeTitle, isActive, withTimeout, originFromUrl, settings, colorFor, patternFor,
    keyFor: origin => PREFIX + origin };
})();
