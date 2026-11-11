(() => {
  if (globalThis.PWARecolorTheme) return;

  globalThis.PWARecolorTheme = class ThemeOverride {
    constructor(doc) {
      this.doc = doc;
      this.color = null;
      this.meta = doc.createElement("meta");
      this.meta.dataset.pwaRecolor = "";
      this.timer = null;
      this.observer = new MutationObserver(records => {
        // Ignore routine app content changes. Watch head replacement as well as
        // theme edits, since SPAs can replace either during navigation.
        if (records.some(record => record.target === this.meta ||
          record.target === doc || record.target === doc.documentElement ||
          doc.head?.contains(record.target))) this.schedule();
      });
    }

    schedule() {
      if (this.timer !== null || !this.color) return;
      // Yield to the app. Never answer a site's MutationObserver with another
      // synchronous write in the same microtask checkpoint.
      this.timer = setTimeout(() => {
        this.timer = null;
        this.reconcile();
      }, 100);
    }

    set(color) {
      clearTimeout(this.timer);
      this.timer = null;
      this.color = color;
      this.observer.disconnect();
      if (!color) {
        this.meta.remove();
        return;
      }
      this.reconcile();
    }

    reconcile() {
      if (!this.color) return;
      this.observer.disconnect();
      const head = this.doc.head;
      if (head) {
        // Setting an attribute to its existing value still fires observers.
        if (this.meta.getAttribute("name") !== "theme-color") this.meta.setAttribute("name", "theme-color");
        if (this.meta.getAttribute("content") !== this.color) this.meta.setAttribute("content", this.color);
        if (this.meta.hasAttribute("media")) this.meta.removeAttribute("media");
        // Chromium chooses the first applicable theme-color. Keeping our own
        // first leaves the site's original tags and live updates intact.
        if (head.querySelector('meta[name="theme-color" i]') !== this.meta) head.prepend(this.meta);
      }
      this.observer.observe(this.doc, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ["name", "content", "media"],
      });
    }
  };
})();
