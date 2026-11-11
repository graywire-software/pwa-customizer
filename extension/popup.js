const R = PWARecolor;
const $ = id => document.getElementById(id);
let origin = null;
let saved = R.settings();
let busy = false;
let tabId = null;
let shortNameMessage = "Reading app name…";
let titleInfoRevision = 0;

function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}

function updateSwatch(color) {
  $("swatch").style.backgroundColor = color;
}

function render() {
  $("enabled").checked = saved.enabled;
  $("enabled").disabled = busy || !origin;
  $("controls").hidden = !saved.enabled;
  $("title-enabled").checked = saved.titleEnabled;
  $("title-enabled").disabled = busy || !origin;
  $("title-controls").hidden = !saved.titleEnabled;
  $("title-form").hidden = !saved.titleEnabled || saved.titleMode !== "custom";
  $("title-modes").disabled = busy;
  document.querySelector(`input[name="title-mode"][value="${saved.titleMode}"]`).checked = true;
  $("short-status").hidden = !saved.titleEnabled || saved.titleMode !== "short";
  $("short-status").textContent = shortNameMessage;
  $("modes").disabled = busy;
  document.querySelector(`input[name="mode"][value="${saved.mode}"]`).checked = true;
  $("custom-form").hidden = saved.mode !== "custom";
  $("hex").value = saved.color;
  $("hex").disabled = busy;
  $("apply").disabled = busy;
  $("hex").removeAttribute("aria-invalid");
  $("hex-error").hidden = true;
  $("page-title").value = saved.title;
  $("page-title").disabled = busy || !origin || !saved.titleEnabled;
  $("apply-title").disabled = busy || !origin || !saved.titleEnabled;
  updateSwatch(saved.color);
}

async function refreshTitleInfo() {
  const version = ++titleInfoRevision;
  if (!saved.titleEnabled || saved.titleMode !== "short") return;
  shortNameMessage = "Reading app name…";
  $("short-status").textContent = shortNameMessage;
  try {
    const info = await R.withTimeout(chrome.tabs.sendMessage(tabId, { type: "get-title-state" }),
      6500, "The app did not respond.");
    if (version !== titleInfoRevision) return;
    const shortAppName = info?.name || "";
    shortNameMessage = shortAppName ? `App name: ${shortAppName}` :
      "Couldn’t detect the app name. Choose Custom page title.";
  } catch {
    if (version !== titleInfoRevision) return;
    shortNameMessage = "Reload your app to detect its name.";
  }
  if (!busy) render();
}

async function persist(next) {
  busy = true;
  render();
  status("Saving…");
  try {
    const response = await chrome.runtime.sendMessage({ type: "save-site", origin, settings: next });
    if (!response?.ok) throw new Error(response?.error || "Could not save. Please try again.");
    saved = R.settings(response.settings);
    status(response.applied ? "Saved." : "Saved. Reload your app to apply changes.");
  } catch (error) {
    status(error.message, true);
  } finally {
    busy = false;
    render();
    refreshTitleInfo();
  }
}

async function saveWithPermission(next) {
  if (busy || !origin) return;
  if (R.isActive(next)) {
    busy = true;
    // Request immediately within the user gesture, before any await.
    try {
      const permission = chrome.permissions.request({ origins: [R.patternFor(origin)] });
      render();
      if (!await permission) {
        status("Site access wasn’t granted. Changes weren’t saved.", true);
        return;
      }
    } catch (error) {
      status(error.message, true);
      return;
    } finally {
      busy = false;
      render();
    }
  }
  await persist(next);
}

$("enabled").addEventListener("change", event => {
  saveWithPermission({ ...saved, enabled: event.target.checked });
});

$("title-enabled").addEventListener("change", event => {
  saveWithPermission({ ...saved, titleEnabled: event.target.checked });
});

$("title-form").addEventListener("submit", event => {
  event.preventDefault();
  if (!saved.titleEnabled || saved.titleMode !== "custom") return;
  saveWithPermission({ ...saved, title: R.sanitizeTitle($("page-title").value) });
});

$("title-modes").addEventListener("change", event => {
  if (!busy && event.target.name === "title-mode") persist({ ...saved, titleMode: event.target.value });
});

$("modes").addEventListener("change", event => {
  if (!busy && event.target.name === "mode") persist({ ...saved, mode: event.target.value });
});

$("hex").addEventListener("input", () => {
  const color = R.sanitizeHex($("hex").value);
  $("hex").removeAttribute("aria-invalid");
  $("hex-error").hidden = true;
  if (color) updateSwatch(color);
});

$("hex").addEventListener("blur", () => {
  const color = R.sanitizeHex($("hex").value);
  if (color) $("hex").value = color;
});

$("custom-form").addEventListener("submit", event => {
  event.preventDefault();
  if (busy) return;
  const color = R.sanitizeHex($("hex").value);
  if (!color) {
    $("hex").setAttribute("aria-invalid", "true");
    $("hex-error").textContent = "Use a hex color like #ABC or #1A2B3C.";
    $("hex-error").hidden = false;
    $("hex").focus();
    return;
  }
  persist({ ...saved, color, mode: "custom" });
});

async function init() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    tabId = tab?.id;
    origin = R.originFromUrl(tab?.url);
    if (!origin) {
      $("site-name").textContent = "Open a website to begin";
      status("Open a website in a regular tab, then click PWA Customizer.");
      render();
      return;
    }
    $("site-name").textContent = new URL(origin).host;
    $("site-name").title = origin;
    const youtube = ['https://www.youtube.com', 'https://youtube.com'].includes(origin);
    if (youtube) await chrome.runtime.sendMessage({ type: 'youtube-pwa-refresh' }).catch(() => {});
    const key = R.keyFor(origin);
    saved = R.settings((await chrome.storage.local.get(key))[key]);
    if (!youtube && R.isActive(saved) && !await chrome.permissions.contains({ origins: [R.patternFor(origin)] })) {
      saved.enabled = false;
      saved.titleEnabled = false;
    }
    render();
    status("");
    refreshTitleInfo();
  } catch (error) {
    origin = null;
    render();
    $("site-name").textContent = "Couldn’t read this website";
    status(error.message, true);
  }
}
init();
chrome.storage.onChanged.addListener((changes, area) => {
  const key = origin && R.keyFor(origin);
  if (area === 'local' && key && changes[key] && !busy) {
    saved = R.settings(changes[key].newValue); render(); refreshTitleInfo();
  }
});
