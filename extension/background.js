importScripts("shared.js", "pwa-sync.js");
const R = PWARecolor;
const SCRIPT_ID = "pwa-recolor-sites";
// Keep the registration ID and storage keys stable for upgrades from 1.0.
let queue = Promise.resolve();
const youtubeSync = YouTubePwaSync.create({ role: 'pwa-customizer', onChange: () => enqueue(reconcile) });

// Serialize registration changes, including changes from two open popups.
function enqueue(task) {
  const next = queue.then(task);
  queue = next.catch(error => console.error("PWA Customizer:", error));
  return next;
}

async function reconcile() {
  const saved = await chrome.storage.local.get(null);
  const matches = new Set();
  const revoked = {};
  for (const [key, value] of Object.entries(saved)) {
    if (!key.startsWith(R.PREFIX) || !R.isActive(value)) continue;
    const origin = R.originFromUrl(key.slice(R.PREFIX.length));
    if (!origin) continue;
    const pattern = R.patternFor(origin);
    if (await chrome.permissions.contains({ origins: [pattern] })) {
      matches.add(pattern);
    } else if (!YouTubePwaSync.isYouTube(origin)) {
      revoked[key] = { ...R.settings(value), enabled: false, titleEnabled: false };
    }
  }
  if (Object.keys(revoked).length) await chrome.storage.local.set(revoked);

  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [SCRIPT_ID] });
  if (!matches.size) {
    if (existing.length) await chrome.scripting.unregisterContentScripts({ ids: [SCRIPT_ID] });
    return;
  }
  const script = {
    id: SCRIPT_ID,
    matches: [...matches],
    js: ["shared.js", "theme.js", "title.js", "app-name.js", "content.js"],
    runAt: "document_start",
    allFrames: false,
    persistAcrossSessions: true,
  };
  if (existing.length) await chrome.scripting.updateContentScripts([script]);
  else await chrome.scripting.registerContentScripts([script]);
}

async function applyToOpenTabs(origin) {
  const tabs = await R.withTimeout(chrome.tabs.query({ url: R.patternFor(origin) }),
    1500, "Open tabs did not respond.");
  // A site may be open in both a normal tab and an installed app window.
  const results = await Promise.allSettled(tabs.filter(tab =>
    tab.id !== undefined && R.originFromUrl(tab.url) === origin
  ).map(tab => R.withTimeout(chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["shared.js", "theme.js", "title.js", "app-name.js", "content.js"],
  }), 1500, "This tab did not respond.")));
  return results.length > 0 && results.every(result => result.status === "fulfilled");
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  // Only extension pages may change settings, never a website's content script.
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL("popup.html") ||
      message?.type !== "save-site") return;
  enqueue(async () => {
    const origin = R.originFromUrl(message.origin);
    if (!origin || origin !== message.origin) throw new Error("This page cannot be customized.");
    if (!["light", "dark", "custom"].includes(message.settings?.mode)) throw new Error("Choose a color mode.");
    if (!R.sanitizeHex(message.settings.color)) throw new Error("Enter a valid hex color.");
    const next = R.settings(message.settings);
    if (R.isActive(next) && !await chrome.permissions.contains({ origins: [R.patternFor(origin)] })) {
      throw new Error("Allow access to this site to enable PWA Customizer.");
    }
    if (YouTubePwaSync.isYouTube(origin)) {
      const settings = await youtubeSync.save(next);
      await reconcile();
      const applied = R.isActive(settings) ? await applyToOpenTabs(origin).catch(() => false) : true;
      return { ok: true, settings, applied };
    }
    const key = R.keyFor(origin);
    const previous = await chrome.storage.local.get(key);
    await chrome.storage.local.set({ [key]: next });
    try {
      await reconcile();
    } catch (error) {
      if (previous[key]) await chrome.storage.local.set(previous);
      else await chrome.storage.local.remove(key);
      await reconcile().catch(() => {});
      throw error;
    }
    // Settings are already committed. One unresponsive PWA must not block this
    // reply or the queue of subsequent saves indefinitely.
    const applied = R.isActive(next) ? await applyToOpenTabs(origin).catch(() => false) : true;
    return { ok: true, settings: next, applied };
  }).then(respond, error => respond({ ok: false, error: error.message }));
  return true;
});

chrome.runtime.onInstalled.addListener(() => { enqueue(reconcile); });
chrome.runtime.onStartup.addListener(() => { enqueue(reconcile); });
chrome.permissions.onRemoved.addListener(() => { enqueue(reconcile); });
