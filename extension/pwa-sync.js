/* Shared with PWA Customizer. Only the two YouTube origins are synchronized. */
globalThis.YouTubePwaSync = (() => {
  const origins = ['https://www.youtube.com', 'https://youtube.com'];
  const keys = origins.map(origin => 'site:' + origin);
  const recordKey = 'youtubePwaSync';
  const type = 'youtube-pwa-sync-v1';
  const isYouTube = origin => origins.includes(origin);

  function create({ role, onChange = () => {} }) {
    const R = PWARecolor;
    const peers = chrome.runtime.getManifest().externally_connectable?.ids || [];
    const writers = [chrome.runtime.id, ...peers];
    let queue = Promise.resolve();
    const enqueue = task => {
      const next = queue.then(task);
      queue = next.catch(() => {});
      return next;
    };
    const same = (a, b) => JSON.stringify(R.settings(a)) === JSON.stringify(R.settings(b));
    const valid = value => value?.version === 1 && Number.isSafeInteger(value.clock) && value.clock >= 0 &&
      writers.includes(value.writer) && value.settings && typeof value.settings === 'object';
    const compare = (a, b) => !a ? -1 : !b ? 1 : a.clock - b.clock || a.writer.localeCompare(b.writer);
    async function write(record) {
      const settings = R.settings(record.settings);
      record = { version: 1, clock: record.clock, writer: record.writer, settings };
      await chrome.storage.local.set({ [recordKey]: record, ...Object.fromEntries(keys.map(key => [key, settings])) });
      Promise.resolve().then(onChange).catch(error => console.warn('YouTube PWA update:', error.message));
      return record;
    }
    async function read() {
      const saved = await chrome.storage.local.get([recordKey, ...keys]);
      if (valid(saved[recordKey])) return saved[recordKey];
      const legacy = keys.find(key => Object.hasOwn(saved, key));
      // An untouched installation never overwrites the other extension's preferences.
      return legacy ? write({ version: 1, clock: 1, writer: chrome.runtime.id, settings: saved[legacy] }) : null;
    }
    async function merge(incoming) {
      const current = await read();
      if (valid(incoming) && compare(incoming, current) > 0) return write(incoming);
      return current;
    }
    async function contact(id, record) {
      try {
        const response = await R.withTimeout(chrome.runtime.sendMessage(id, { type, record }), 1800, 'Companion unavailable');
        if (response?.protocol !== 1 || response.role === role) return false;
        await enqueue(() => merge(response.record));
        return true;
      } catch { return false; }
    }
    async function sync() {
      const record = await enqueue(read);
      const connected = await Promise.all(peers.map(id => contact(id, record)));
      return connected.some(Boolean);
    }
    async function save(value) {
      const record = await enqueue(async () => {
        const current = await read();
        return write({ version: 1, clock: Math.max(Date.now(), (current?.clock || 0) + 1),
          writer: chrome.runtime.id, settings: value });
      });
      // Network-free extension messages happen outside the local write queue so
      // simultaneous saves cannot deadlock the two workers.
      await Promise.all(peers.map(id => contact(id, record)));
      return R.settings((await enqueue(read))?.settings);
    }
    chrome.runtime.onMessageExternal.addListener((message, sender, respond) => {
      if (!peers.includes(sender.id) || sender.url !== `chrome-extension://${sender.id}/background.js` ||
          message?.type !== type || (message.record !== null && !valid(message.record))) return;
      enqueue(() => merge(message.record)).then(record => respond({ protocol: 1, role, record }),
        () => respond({ protocol: 1, role, error: 'Could not save settings' }));
      return true;
    });
    chrome.runtime.onMessage.addListener((message, sender, respond) => {
      if (sender.id !== chrome.runtime.id) return;
      const popup = sender.url === chrome.runtime.getURL('popup.html');
      let origin;
      try { origin = new URL(sender.url).origin; } catch { return; }
      if (message?.type === 'youtube-pwa-refresh' && (popup || isYouTube(origin))) {
        sync().then(connected => respond({ connected }), () => respond({ connected: false }));
        return true;
      }
      if (message?.type === 'youtube-pwa-save' && popup && role === 'youtools') {
        if (!R.sanitizeHex(message.settings?.color)) { respond({ ok: false, error: 'Enter a valid hex color.' }); return; }
        save(message.settings).then(settings => respond({ ok: true, settings }),
          () => respond({ ok: false, error: 'Could not save app settings.' }));
        return true;
      }
    });
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'local' || changes[recordKey]) return;
      const key = keys.find(key => changes[key]);
      if (!key) return;
      // Handles legacy saves and storage edits without echoing mirrored writes.
      enqueue(async () => {
        const current = await read(), value = changes[key].newValue;
        if (current && same(current.settings, value)) return;
        await write({ version: 1, clock: Math.max(Date.now(), (current?.clock || 0) + 1),
          writer: chrome.runtime.id, settings: value });
      }).then(sync).catch(() => {});
    });
    chrome.runtime.onInstalled.addListener(() => { sync().catch(() => {}); });
    chrome.runtime.onStartup.addListener(() => { sync().catch(() => {}); });
    return { save, sync };
  }
  return { create, isYouTube, keys, recordKey };
})();
