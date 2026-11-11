(() => {
  // Dynamic registration and immediate application can overlap.
  if (globalThis.__pwaRecolorRunning) return;
  globalThis.__pwaRecolorRunning = true;
  const R = PWARecolor;
  const key = R.keyFor(location.origin);
  const youtube = ['https://www.youtube.com', 'https://youtube.com'].includes(location.origin);
  const theme = new PWARecolorTheme(document);
  const title = new PWACustomizerTitle(document);
  let revision = 0;
  let current = R.settings();
  let nameRevision = 0;
  let nameSignature = null;
  let shortName = "";
  let nameTask = Promise.resolve();
  let nameTimer = null;

  const refreshShortName = () => {
    const signature = PWACustomizerAppName.signature(document);
    if (signature === nameSignature) return;
    nameSignature = signature;
    const version = ++nameRevision;
    nameTask = PWACustomizerAppName.resolve(document).then(name => {
      // A slow manifest response must not re-enable an old mode or setting.
      if (version !== nameRevision) return;
      shortName = name;
      title.set(name);
    });
  };
  const nameObserver = new MutationObserver(records => {
    if (records.some(record => record.target === document ||
      record.target === document.documentElement || document.head?.contains(record.target))) {
      if (nameTimer === null) {
        nameTimer = setTimeout(() => {
          nameTimer = null;
          if (current.titleEnabled && current.titleMode === "short") refreshShortName();
        }, 100);
      }
    }
  });
  const applyLocal = value => {
    const saved = R.settings(value);
    current = saved;
    theme.set(saved.enabled ? R.colorFor(saved) : null);
    nameRevision++;
    clearTimeout(nameTimer);
    nameTimer = null;
    nameObserver.disconnect();
    nameSignature = null;
    if (youtube && saved.titleEnabled && saved.titleMode === "short") {
      shortName = 'YouTube';
      title.set(shortName);
    } else if (saved.titleEnabled && saved.titleMode === "short") {
      nameObserver.observe(document, { subtree: true, childList: true, attributes: true,
        attributeFilter: ["rel", "href", "crossorigin", "name", "content"] });
      refreshShortName();
    } else {
      title.set(saved.titleEnabled ? saved.title : "");
    }
  };
  let applyRevision = 0;
  const apply = async value => {
    const version = ++applyRevision;
    if (youtube) {
      // YouTools owns the YouTube DOM when present. Mirrored values alone would
      // leave two observers competing for theme tags and original page titles.
      const peer = await R.withTimeout(chrome.runtime.sendMessage({ type: 'youtube-pwa-refresh' }),
        2200, 'Companion unavailable').catch(() => null);
      if (version !== applyRevision) return;
      if (peer?.connected) {
        current = R.settings(value);
        shortName = 'YouTube';
        theme.set(null); title.set('');
        return;
      }
    }
    if (version === applyRevision) applyLocal(value);
  };
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message?.type !== "get-title-state" || sender.id !== chrome.runtime.id ||
        sender.url !== chrome.runtime.getURL("popup.html")) return;
    nameTask.then(() => respond({ name: shortName, titleMode: current.titleMode }));
    return true;
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && Object.hasOwn(changes, key)) {
      revision++;
      apply(changes[key].newValue);
    }
  });
  // A storage event may arrive while the initial read is in flight.
  const initialRevision = revision;
  chrome.storage.local.get(key).then(saved => {
    if (revision === initialRevision) apply(saved[key]);
  }).catch(() => {
    theme.set(null);
    title.set("");
  });
  if (youtube) {
    window.addEventListener('focus', () => {
      try { chrome.storage.local.get(key).then(saved => apply(saved[key])).catch(() => {}); }
      catch { theme.set(null); title.set(''); }
    });
  }
})();
