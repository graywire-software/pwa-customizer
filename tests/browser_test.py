"""Integration checks in an isolated Brave profile; never touches personal tabs.

Run: python tests/browser_test.py
Set BROWSER_PATH to test a different Chromium executable.
The temporary test copy pregrants localhost access because headless Chromium
cannot show the native optional-permission prompt. Only popup tab selection is
substituted; storage, messages, registration, and content scripts use real APIs.
"""
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BROWSER = os.environ.get("BROWSER_PATH", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
HTML = b'''<!doctype html><html><head><title>Recolor test app</title>
<link rel="manifest" href="/app.webmanifest">
<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#EEEEEE" media="(prefers-color-scheme: light)">
</head><body><h1>Test web app</h1><p>Original page content</p></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/manifest+json" if self.path.endswith(".webmanifest") else "text/html")
        self.end_headers()
        if self.path == "/app.webmanifest":
            self.wfile.write(b'{"short_name":"Messages","name":"Google Messages for web"}')
        elif self.path == "/name-only.webmanifest":
            self.wfile.write(b'{"name":"Name Only"}')
        elif self.path == "/invalid.webmanifest":
            self.wfile.write(b'not valid JSON')
        elif self.path == "/slow.webmanifest":
            slow_requested.set()
            slow_release.wait(5)
            self.wfile.write(b'{"short_name":"Slow App"}')
        else:
            self.wfile.write(HTML)

    def log_message(self, *args):
        pass


slow_requested = threading.Event()
slow_release = threading.Event()
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f"http://127.0.0.1:{server.server_port}"


def overridden(page, color):
    expect(page.locator('meta[data-pwa-recolor]')).to_have_count(1)
    expect(page.locator('meta[name="theme-color"]').first).to_have_attribute("content", color)


with tempfile.TemporaryDirectory(prefix="pwa-recolor-tests-") as temp, sync_playwright() as p:
    extension = Path(temp) / "extension"
    shutil.copytree(ROOT / "extension", extension)
    manifest = json.loads((extension / "manifest.json").read_text())
    manifest["host_permissions"] = ["http://127.0.0.1/*"]
    (extension / "manifest.json").write_text(json.dumps(manifest))
    profile = str(Path(temp) / "profile")
    launch = dict(executable_path=BROWSER, headless=True, color_scheme="dark",
                  args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                        f"--explicitly-allowed-ports={server.server_port}", "--no-first-run"])
    context = p.chromium.launch_persistent_context(profile, **launch)
    worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
    extension_id = worker.url.split("/")[2]
    page = context.pages[0]
    page.goto(origin)
    page.bring_to_front()
    tab_id = worker.evaluate("async () => (await chrome.tabs.query({active:true, currentWindow:true}))[0].id")
    second = context.new_page()
    second.goto(origin + "/another-path")
    other = context.new_page()
    other.goto(origin.replace("127.0.0.1", "localhost"))
    popup = context.new_page()
    popup_errors = []
    popup.on("pageerror", lambda e: popup_errors.append(str(e)))
    popup.add_init_script(f'''const realQuery = chrome.tabs.query.bind(chrome.tabs);
      chrome.tabs.query = query => query.active && query.currentWindow
        ? Promise.resolve([{{id:{tab_id},url:{json.dumps(origin)}}}]) : realQuery(query);''')
    popup.goto(f"chrome-extension://{extension_id}/popup.html")
    expect(popup.locator("#enabled")).to_be_enabled()
    expect(popup.locator("#enabled")).not_to_be_checked()
    expect(popup.locator("#controls")).to_be_hidden()
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    expect(popup.locator("#page-title")).to_have_value("")
    expect(popup.locator("#title-enabled")).not_to_be_checked()
    expect(popup.locator("#title-form")).to_be_hidden()
    expect(page).to_have_title("Recolor test app")
    print("PASS: disabled by default")

    # The input accepts only whole opaque hex colors, never CSS or markup.
    popup.evaluate('''() => {
      const cases = [[" abc ", "#AABBCC"], ["#12aBef", "#12ABEF"], ["000", "#000000"],
        ["123456", "#123456"], ["#abcd", null], ["#12345678", null], ["red", null],
        ["##abc", null], ["#12 3456", null], ["<script>", null], ["#abc; color:red", null],
        ["url(https://example.com)", null], [null, null], [123, null], ["", null]];
      for (const [input, expected] of cases) {
        if (PWARecolor.sanitizeHex(input) !== expected) throw Error(`Bad sanitization: ${input}`);
      }
      const old = PWARecolor.settings({enabled:true, mode:'custom', color:'#123456'});
      if (!old.enabled || old.mode !== 'custom' || old.color !== '#123456' || old.title !== '') {
        throw Error('Existing 1.0 settings must be preserved');
      }
      if (old.titleEnabled || PWARecolor.settings().titleEnabled ||
          !PWARecolor.settings({title:'Google Messages'}).titleEnabled ||
          PWARecolor.settings({title:'Google Messages', titleEnabled:false}).titleEnabled ||
          PWARecolor.isActive({title:'Google Messages', titleEnabled:false}) ||
          !PWARecolor.isActive({title:'', titleEnabled:true})) {
        throw Error('Title toggle defaults and migration must respect explicit choices');
      }
      if (PWARecolor.settings().titleMode !== 'short' ||
          PWARecolor.settings({title:'Google Messages'}).titleMode !== 'custom' ||
          PWARecolor.settings({titleEnabled:true, title:''}).titleMode !== 'custom') {
        throw Error('Existing title choices must migrate to Custom mode');
      }
    }''')
    print("PASS: hex normalization and rejection of unsafe/invalid values")

    # A denied permission on the title switch must not reveal or enable its UI.
    popup.evaluate("globalThis.requestPermission = chrome.permissions.request; chrome.permissions.request = async () => false")
    popup.locator("#title-enabled").click()
    expect(popup.locator("#status")).to_contain_text("wasn’t granted")
    expect(popup.locator("#title-enabled")).not_to_be_checked()
    expect(popup.locator("#title-form")).to_be_hidden()
    popup.evaluate("() => { chrome.permissions.request = globalThis.requestPermission; }")
    print("PASS: title permission denial leaves the toggle off and title controls hidden")

    popup.locator("#enabled").click()
    expect(popup.locator("#controls")).to_be_visible()
    expect(popup.locator("#status")).to_have_text("Saved.")
    overridden(page, "#202124")
    overridden(second, "#202124")
    expect(other.locator("meta[data-pwa-recolor]")).to_have_count(0)
    assert worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    print("PASS: enable applies dark to all same-origin tabs, leaves other sites alone")

    popup.locator('input[value="light"]').click()
    overridden(page, "#F5F5F5")
    popup.locator('input[name="mode"][value="custom"]').click()
    expect(popup.locator("#hex")).to_be_enabled()
    popup.locator("#hex").fill(" aBc ")
    popup.locator("#apply").click()
    expect(popup.locator("#hex")).to_have_value("#AABBCC")
    overridden(page, "#AABBCC")
    expect(popup.locator("#swatch")).to_have_css("background-color", "rgb(170, 187, 204)")
    popup.locator("#hex").fill("#12345Z")
    popup.locator("#apply").click()
    expect(popup.locator("#hex-error")).to_be_visible()
    overridden(page, "#AABBCC")
    popup.locator("#hex").fill("#273449")
    popup.locator("#hex").press("Enter")
    overridden(page, "#273449")
    print("PASS: light/custom modes, color swatch, normalization, and invalid input preserve last color")

    # The page keeps ownership of its original tags, including live edits.
    page.evaluate('''() => {
      document.querySelector('meta:not([data-pwa-recolor])').content = '#112233';
      const tag = document.createElement('meta');
      tag.name = 'theme-color'; tag.content = '#FF0000'; document.head.prepend(tag);
      history.pushState({}, '', '/spa-route');
    }''')
    overridden(page, "#273449")
    page.evaluate("document.querySelector('[data-pwa-recolor]').remove()")
    overridden(page, "#273449")
    page.evaluate('''() => {
      const head = document.createElement('head');
      head.innerHTML = '<meta name="theme-color" content="#445566">';
      document.head.replaceWith(head);
    }''')
    overridden(page, "#273449")
    print("PASS: survives SPA changes, competing tags, removal, and head replacement")

    # Reinjection does not duplicate observers/tags; disabling reveals current site color.
    popup.locator('input[value="dark"]').click()
    overridden(page, "#202124")
    popup.locator("#enabled").click()
    expect(popup.locator("#status")).to_have_text("Saved.")
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    expect(second.locator("meta[data-pwa-recolor]")).to_have_count(0)
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#445566")
    assert not worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    print("PASS: disabling restores current site color and removes automatic injection")

    # Denial UI uses a substitute return value; the native prompt needs manual testing.
    popup.evaluate("globalThis.requestPermission = chrome.permissions.request; chrome.permissions.request = async () => false")
    popup.locator("#enabled").click()
    expect(popup.locator("#status")).to_contain_text("wasn’t granted")
    expect(popup.locator("#enabled")).not_to_be_checked()
    popup.evaluate("() => { chrome.permissions.request = globalThis.requestPermission; }")
    popup.locator("#enabled").click()
    expect(popup.locator("#status")).to_have_text("Saved.")
    popup.locator('input[name="mode"][value="custom"]').click()
    overridden(page, "#273449")
    page.reload()
    overridden(page, "#273449")
    fresh = context.new_page()
    fresh.goto(origin + "/fresh")
    overridden(fresh, "#273449")
    popup.reload()
    expect(popup.locator("#enabled")).to_be_checked()
    expect(popup.locator("#hex")).to_have_value("#273449")
    print("PASS: permission-denial UI, reload, new tabs, and saved popup state")

    # Title works independently of color, and clearing restores the app's latest title.
    popup.locator("#enabled").click()
    expect(popup.locator("#controls")).to_be_hidden()
    expect(popup.locator("#title-form")).to_be_hidden()
    popup.evaluate('''() => {
      globalThis.titlePermissionRequests = [];
      globalThis.requestPermission = chrome.permissions.request;
      chrome.permissions.request = permissions => {
        titlePermissionRequests.push(permissions);
        return globalThis.requestPermission(permissions);
      };
    }''')
    popup.locator("#title-enabled").click()
    expect(popup.locator("#title-controls")).to_be_visible()
    expect(popup.locator("#title-form")).to_be_hidden()
    expect(popup.locator("#page-title")).to_have_value("")
    expect(page).to_have_title("Messages")
    expect(second).to_have_title("Messages")
    expect(popup.locator("#short-status")).to_have_text("App name: Messages")
    expect(popup.get_by_role("switch", name="Change page title")).to_be_checked()
    popup.locator(".tooltip-anchor").focus()
    expect(popup.get_by_role("tooltip")).to_be_visible()
    expect(popup.get_by_role("tooltip")).to_contain_text("Sets the page title to the app name")
    assert popup.evaluate("titlePermissionRequests") == [{"origins": ["http://127.0.0.1/*"]}]
    popup.evaluate("() => { chrome.permissions.request = globalThis.requestPermission; }")
    print("PASS: title toggle requests site access before any title is entered")
    popup.locator('input[name="title-mode"][value="custom"]').click()
    expect(popup.locator("#title-form")).to_be_visible()
    expect(page).to_have_title("Recolor test app")
    expect(popup.locator("#title-help")).to_contain_text("Browser may not allow app name to be hidden")
    popup.locator("#page-title").fill("  Google   Messages  ")
    popup.locator("#page-title").press("Enter")
    expect(popup.locator("#page-title")).to_have_value("Google Messages")
    expect(page).to_have_title("Google Messages")
    expect(second).to_have_title("Google Messages")
    expect(other).to_have_title("Recolor test app")
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    assert worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    page.reload()
    expect(page).to_have_title("Google Messages")
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    page.evaluate("document.title = '(2) Messages - Conversations'")
    expect(page).to_have_title("Google Messages")
    popup.locator("#title-enabled").click()
    expect(popup.locator("#title-form")).to_be_hidden()
    expect(page).to_have_title("(2) Messages - Conversations")
    assert not worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    popup.reload()
    expect(popup.locator("#title-enabled")).not_to_be_checked()
    expect(popup.locator("#title-form")).to_be_hidden()
    expect(popup.locator("#page-title")).to_have_value("Google Messages")
    popup.locator("#title-enabled").click()
    expect(popup.locator("#title-form")).to_be_visible()
    expect(page).to_have_title("Google Messages")
    print("PASS: title switch restores the site title, remembers custom text, and persists off/on")
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("(2) Messages - Conversations")
    expect(second).to_have_title("Recolor test app")
    # An enabled but empty title remains ready for input and future visits.
    assert worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    print("PASS: title-only mode, origin isolation, reload, and restoration of latest site title")

    # Treat user text literally, including strings that look like HTML.
    literal = '<img src=x onerror="alert(1)"> & Messages'
    popup.locator("#page-title").fill(literal)
    popup.locator("#apply-title").click()
    expect(page).to_have_title(literal)
    expect(page.locator("img")).to_have_count(0)
    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    page.evaluate("document.querySelector('title').firstChild.data = 'Another conversation'")
    expect(page).to_have_title("Google Messages")
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Another conversation")
    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    page.evaluate('''() => {
      const head = document.createElement('head');
      head.innerHTML = '<title>New conversation</title><meta name="theme-color" content="#123456">';
      document.head.replaceWith(head);
    }''')
    expect(page).to_have_title("Google Messages")
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("New conversation")
    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    page.evaluate("document.querySelector('title').remove()")
    expect(page).to_have_title("Google Messages")
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    expect(page.locator("title")).to_have_count(0)
    print("PASS: plain-text titles, title text edits/removal, head replacement, and restoration")

    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    page.evaluate("document.title = 'Google Messages'")
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    # The title is identical before/after this save; waiting on its text alone
    # would let the next page mutation race the setting's storage event.
    expect(popup.locator("#status")).to_have_text("Saved.")
    expect(page).to_have_title("Google Messages")
    page.evaluate("document.querySelector('title').remove()")
    print("PASS: restores an app-written title even when it matches the custom title")

    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    popup.locator("#enabled").click()
    overridden(page, "#273449")
    expect(page).to_have_title("Google Messages")
    # Clearing only the title must leave the color active and registered.
    popup.locator("#page-title").fill("")
    popup.locator("#apply-title").click()
    expect(page.locator("title")).to_have_count(0)
    overridden(page, "#273449")
    assert worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    popup.locator("#page-title").fill("Google Messages")
    popup.locator("#apply-title").click()
    expect(page).to_have_title("Google Messages")
    popup.reload()
    expect(popup.locator("#page-title")).to_have_value("Google Messages")
    expect(popup.locator("#title-enabled")).to_be_checked()
    expect(popup.locator("h1")).to_have_text("PWA Customizer")
    expect(popup.locator('label[for="hex"]')).to_have_text("Custom color")
    print("PASS: title and color are independent; title and new branding persist in popup")

    # Turning title customization off must keep the color active, and vice versa.
    popup.locator("#title-enabled").click()
    expect(popup.locator("#title-form")).to_be_hidden()
    expect(page.locator("title")).to_have_count(0)
    overridden(page, "#273449")
    assert worker.evaluate("chrome.scripting.getRegisteredContentScripts()")
    popup.locator("#title-enabled").click()
    expect(page).to_have_title("Google Messages")
    popup.locator("#enabled").click()
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    expect(page).to_have_title("Google Messages")
    expect(popup.locator("#title-form")).to_be_visible()
    page.reload()
    expect(page).to_have_title("Google Messages")
    expect(page.locator("meta[data-pwa-recolor]")).to_have_count(0)
    popup.locator("#enabled").click()
    overridden(page, "#273449")
    print("PASS: independent color/title switches across reloads")

    # Short mode resolves the manifest name and preserves the saved custom text.
    popup.locator('input[name="title-mode"][value="short"]').click()
    expect(page).to_have_title("Messages")
    expect(popup.locator("#title-form")).to_be_hidden()
    page.evaluate("document.title = '(3) Conversation'")
    expect(page).to_have_title("Messages")
    popup.locator('input[name="title-mode"][value="custom"]').click()
    expect(page).to_have_title("Google Messages")
    expect(popup.locator("#page-title")).to_have_value("Google Messages")
    popup.locator('input[name="title-mode"][value="short"]').click()
    expect(page).to_have_title("Messages")
    page.evaluate("document.querySelector('link[rel=manifest]').href = '/name-only.webmanifest'")
    expect(page).to_have_title("Name Only")
    page.evaluate('''() => {
      document.querySelector('link[rel=manifest]').href = '/invalid.webmanifest';
      const name = document.createElement('meta');
      name.name = 'application-name'; name.content = 'Metadata App'; document.head.append(name);
    }''')
    expect(page).to_have_title("Metadata App")
    page.evaluate("document.querySelector('meta[name=application-name]').remove()")
    expect(page).to_have_title("(3) Conversation")
    popup.reload()
    expect(popup.locator("#short-status")).to_contain_text("Couldn’t detect the app name")
    print("PASS: Short mode uses manifest short_name/name, metadata fallback, and handles missing names")

    # A response from an old Short-mode request must not overwrite Custom mode.
    page.evaluate("document.querySelector('link[rel=manifest]').href = '/slow.webmanifest'")
    assert slow_requested.wait(3), "Expected a manifest request"
    popup.locator('input[name="title-mode"][value="custom"]').click()
    expect(page).to_have_title("Google Messages")
    slow_release.set()
    popup.evaluate(f"chrome.tabs.sendMessage({tab_id}, {{type:'get-title-state'}})")
    expect(page).to_have_title("Google Messages")
    popup.locator('input[name="title-mode"][value="short"]').click()
    expect(page).to_have_title("Slow App")
    popup.locator("#title-enabled").click()
    expect(page).to_have_title("(3) Conversation")
    popup.locator("#title-enabled").click()
    expect(page).to_have_title("Slow App")
    page.reload()
    expect(page).to_have_title("Messages")
    popup.reload()
    expect(popup.locator('input[name="title-mode"][value="short"]')).to_be_checked()
    expect(popup.locator("#short-status")).to_have_text("App name: Messages")
    print("PASS: async mode changes, Short-mode off/on, and reload persistence")

    # Reproduce an app's head manager pushing back during Custom/Short switches.
    page.evaluate('''() => {
      globalThis.siteTitleWrites = 0;
      globalThis.siteTitleManager = new MutationObserver(() => {
        if (document.title !== 'App managed title' && siteTitleWrites < 500) {
          siteTitleWrites++;
          document.title = 'App managed title';
        }
      });
      siteTitleManager.observe(document.head, {subtree:true, childList:true});
    }''')
    for title_mode in ("custom", "short", "custom", "short"):
        page.evaluate("siteTitleWrites = 0; globalThis.siteTitleStart = performance.now()")
        popup.locator(f'input[name="title-mode"][value="{title_mode}"]').click()
        expect(popup.locator(f'input[name="title-mode"][value="{title_mode}"]')).to_be_checked()
        expect(popup.locator("#status")).to_have_text("Saved.")
        timing = page.evaluate("async () => { await new Promise(r => setTimeout(r, 150)); return {writes: siteTitleWrites, elapsed: performance.now() - siteTitleStart}; }")
        writes = timing['writes']
        print('Title switch timing:', title_mode, timing)
        # Include the time spent waiting for the browser to save/inject. On
        # Windows, Short-mode injection can take over a second before this
        # assertion starts; the observer still retries only once per 100 ms.
        limit = math.ceil(timing['elapsed'] / 100) + 2
        assert writes <= limit, f"Mode switch caused {writes} rewrites in {timing['elapsed']} ms (limit {limit})"
    page.evaluate("siteTitleManager.disconnect()")
    expect(page).to_have_title("Messages")
    print("PASS: repeated Custom/Short switches stay responsive with a reactive page-title manager")

    # Simulate a tab that never acknowledges injection. Saving must still finish,
    # keep the preference, and allow another save through the worker's queue.
    worker.evaluate(f'''() => {{
      globalThis.realExecuteScript = chrome.scripting.executeScript.bind(chrome.scripting);
      chrome.scripting.executeScript = options => options.target.tabId === {tab_id}
        ? new Promise(() => {{}}) : realExecuteScript(options);
    }}''')
    for title_mode in ("custom", "short"):
        popup.locator(f'input[name="title-mode"][value="{title_mode}"]').click()
        expect(popup.locator("#status")).to_have_text("Saved. Reload your app to apply changes.", timeout=4000)
        expect(popup.locator(f'input[name="title-mode"][value="{title_mode}"]')).to_be_checked()
        expect(popup.locator("#title-enabled")).to_be_enabled()
    worker.evaluate("() => { chrome.scripting.executeScript = globalThis.realExecuteScript; }")
    print("PASS: an unresponsive tab cannot stall saving or block subsequent saves")

    output = ROOT / "test-results"
    output.mkdir(exist_ok=True)
    popup.screenshot(path=str(output / "popup-short.png"), clip={"x": 0, "y": 0, "width": 352, "height": popup.locator("body").bounding_box()["height"]})
    popup.locator('input[name="title-mode"][value="custom"]').click()
    expect(popup.locator("#title-form")).to_be_visible()
    assert popup.locator("body").bounding_box()["height"] <= 600, "Exceeds Chromium popup height"
    popup.screenshot(path=str(output / "popup-dark.png"), clip={"x": 0, "y": 0, "width": 352, "height": popup.locator("body").bounding_box()["height"]})
    popup.emulate_media(color_scheme="light")
    popup.screenshot(path=str(output / "popup-light.png"), clip={"x": 0, "y": 0, "width": 352, "height": popup.locator("body").bounding_box()["height"]})
    popup.locator('input[name="title-mode"][value="short"]').click()
    expect(page).to_have_title("Messages")
    assert not popup_errors, popup_errors
    context.close()

    # Persistent registration must work across a completely new browser process.
    context = p.chromium.launch_persistent_context(profile, **launch)
    page = context.new_page()
    page.goto(origin)
    overridden(page, "#273449")
    expect(page).to_have_title("Messages")
    context.close()
    print("PASS: survives browser restart")

server.shutdown()
print("All browser checks passed. Native macOS PWA chrome and permission prompt require a manual check.")
