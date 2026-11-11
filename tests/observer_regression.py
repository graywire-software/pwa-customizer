"""Reproduce a site's reactive head manager fighting extension overrides.

The fixture caps its own rewrites so the broken implementation fails safely
instead of hanging the test browser. Run with the development Python env.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BROWSER = os.environ.get("BROWSER_PATH", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=BROWSER, headless=True)
    page = browser.new_page()
    page.set_content('<html><head><title>Website title</title></head><body><button>Click</button></body></html>')
    for script in ("theme.js", "title.js"):
        page.add_script_tag(path=str(ROOT / "extension" / script))
    result = page.evaluate('''async () => {
      let siteWrites = 0, heartbeats = 0;
      const timer = setInterval(() => heartbeats++, 10);
      const override = new PWACustomizerTitle(document);
      override.set('Custom title');
      const app = new MutationObserver(() => {
        if (document.title !== 'Website title' && siteWrites < 500) {
          siteWrites++;
          document.title = 'Website title';
        }
      });
      app.observe(document.head, {childList:true, subtree:true});
      // Switching from Custom to Short while the app owns its title.
      override.set('Messages');
      await new Promise(resolve => setTimeout(resolve, 350));
      app.disconnect();
      override.set('');
      clearInterval(timer);
      await new Promise(resolve => setTimeout(resolve, 150));
      if (document.title !== 'Website title') throw Error('A pending retry survived disable');
      return {siteWrites, heartbeats};
    }''')
    print("Reactive title manager:", result)
    assert result["siteWrites"] <= 5, "Title observers form an unbounded rewrite loop"
    assert result["heartbeats"] >= 10, "Page timers must continue running"

    result = page.evaluate('''async () => {
      const theme = new PWARecolorTheme(document);
      theme.set('#202124');
      let writes = 0;
      const watch = new MutationObserver(records => writes += records.length);
      watch.observe(document.querySelector('[data-pwa-recolor]'), {attributes:true});
      document.head.prepend(document.createElement('style'));
      document.title = 'A routine title update';
      await new Promise(resolve => setTimeout(resolve, 200));
      watch.disconnect();
      theme.set(null);
      return writes;
    }''')
    print('Theme writes after unrelated head updates:', result)
    assert result == 0, 'Unchanged theme attributes must not retrigger the app'

    result = page.evaluate('''async () => {
      let removals = 0;
      const app = new MutationObserver(() => {
        const meta = document.querySelector('[data-pwa-recolor]');
        if (meta && removals < 500) { removals++; meta.remove(); }
      });
      app.observe(document.head, {childList:true});
      const theme = new PWARecolorTheme(document);
      theme.set('#202124');
      await new Promise(resolve => setTimeout(resolve, 350));
      app.disconnect();
      theme.set(null);
      await new Promise(resolve => setTimeout(resolve, 150));
      if (document.querySelector('[data-pwa-recolor]')) throw Error('Theme retry survived disable');
      return removals;
    }''')
    print('Reactive theme manager:', result)
    assert result <= 5, 'Theme observers must yield instead of looping'
    browser.close()
print("Observer regression checks passed")
