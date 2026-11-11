(() => {
  if (globalThis.PWACustomizerTitle) return;

  globalThis.PWACustomizerTitle = class TitleOverride {
    constructor(doc) {
      this.doc = doc;
      this.value = "";
      this.siteTitle = "";
      this.createdTitle = null;
      this.timer = null;
      this.observer = new MutationObserver(records => {
        if (records.some(record => record.target === doc ||
          record.target === doc.documentElement || doc.head?.contains(record.target))) {
          this.captureSiteTitle(records.some(record => record.target.nodeName === "TITLE" ||
            record.target.parentNode?.nodeName === "TITLE" ||
            [...record.addedNodes, ...record.removedNodes].some(node =>
              node.nodeName === "TITLE" || node.nodeName === "HEAD")));
          if (this.doc.title !== this.value) this.schedule();
        }
      });
    }

    schedule() {
      if (this.timer !== null || !this.value) return;
      // A reactive app may immediately undo the title. Bound retries and let
      // input, rendering, storage events, and extension messages run between them.
      this.timer = setTimeout(() => {
        this.timer = null;
        if (this.value) this.reconcile();
      }, 100);
    }

    captureSiteTitle(writtenBySite = false) {
      // Remember the app's latest title, including navigation/unread updates,
      // without mistaking our own previous override for the app's title.
      if (writtenBySite || this.doc.title !== this.value) this.siteTitle = this.doc.title;
    }

    set(value) {
      clearTimeout(this.timer);
      this.timer = null;
      if (this.value) this.captureSiteTitle();
      else if (value) this.siteTitle = this.doc.title;
      const wasActive = !!this.value;
      this.value = value;
      this.observer.disconnect();
      if (!value) {
        if (wasActive) {
          if (this.createdTitle?.isConnected && !this.siteTitle) this.createdTitle.remove();
          else this.doc.title = this.siteTitle;
        }
        this.createdTitle = null;
        return;
      }
      this.reconcile();
    }

    reconcile() {
      this.observer.disconnect();
      if (this.doc.head && this.doc.title !== this.value) {
        if (!this.doc.head.querySelector("title")) {
          this.createdTitle = this.doc.createElement("title");
          this.doc.head.append(this.createdTitle);
        }
        this.doc.title = this.value;
      }
      this.observer.observe(this.doc, { subtree: true, childList: true, characterData: true });
    }
  };
})();
