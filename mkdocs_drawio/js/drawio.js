(function overrideEditUrlEarly() {
  document.addEventListener("DOMContentLoaded", () => {
    const first = document.querySelector("div.mxgraph");
    if (!first) return;
    try {
      const config = JSON.parse(first.getAttribute("data-mxgraph") || '{}');
      if (typeof config.edit === "string" && config.edit !== "_blank") {
        console.log("[drawio.js] ✅ Overriding editBlankUrl to:", config.edit);
        GraphViewer.prototype.editBlankUrl = config.edit;
        GraphViewer.prototype.allowOpener = true;
      }
    } catch (err) {
      console.warn("[drawio.js] ⚠️ Failed to parse editBlankUrl from config", err);
    }
  });
})();

(function injectEditFloatingButton() {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("div.mxgraph").forEach(container => {
      try {
        const config = JSON.parse(container.getAttribute("data-mxgraph") || "{}");
        if (!(config.edit && config.toolbar?.includes("edit"))) return;

        const wrapper = container.closest(".drawio-container");
        if (!wrapper || wrapper.querySelector(".drawio-floating-edit")) return;

        const btn = document.createElement("a");
        btn.className = "drawio-floating-edit";
        btn.href = config.edit;
        btn.target = "_blank";
        btn.title = "Edit this diagram";

        btn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path fill="currentColor" d="M10 20H6V4h7v5h5v3.1l2-2V8l-6-6H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h4zm10.2-7c.1 0 .3.1.4.2l1.3 1.3c.2.2.2.6 0 .8l-1 1-2.1-2.1 1-1c.1-.1.2-.2.4-.2m0 3.9L14.1 23H12v-2.1l6.1-6.1z"/>
          </svg>
        `;

        wrapper.appendChild(btn);
      } catch (err) {
        console.warn("[drawio.js] Failed to inject floating edit button:", err);
      }
    });
  });
})();

(function loadDrawioFonts() {
  const fonts = [
    { fontFamily: "Roboto Medium", fontUrl: "/fonts/Roboto-Medium.ttf" },
    { fontFamily: "Roboto", fontUrl: "/fonts/Roboto-Regular.ttf" },
    { fontFamily: "Roboto Condensed", fontUrl: "/fonts/RobotoCondensed-Regular.ttf" },
    { fontFamily: "Roboto Mono", fontUrl: "/fonts/RobotoMono-Regular.ttf" }
  ];
  fonts.forEach(f => {
    const face = new FontFace(f.fontFamily, `url(${f.fontUrl})`);
    face.load().then(loaded => {
      document.fonts.add(loaded);
    }).catch(err => {
      console.warn(`[drawio.js] ❌ Failed to load ${f.fontFamily}`, err);
    });
  });
})();

(function waitForDrawioReady(attempts = 0) {
  if (typeof GraphViewer !== "undefined" && typeof document$?.subscribe === "function") {
    document$.subscribe(() => {
      GraphViewer.processElements();
      hideExportPrintButtons();
    });
  } else if (attempts < 50) {
    setTimeout(() => waitForDrawioReady(attempts + 1), 200);
  } else {
    console.warn("[drawio.js] ❌ Timeout: Drawio viewer not ready after 50 attempts");
  }
})();

// 🚫 Remove Export/Print buttons
function hideExportPrintButtons() {
  const selectors = ['span[title="Export"]', 'span[title="Print"]'];
  const hidden = new Set();

  const hideButtonIfFound = () => {
    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(el => {
        if (!hidden.has(el)) {
          el.style.display = 'none';
          hidden.add(el);
        }
      });
    });
  };

  const observer = new MutationObserver(() => {
    hideButtonIfFound();
    if (hidden.size >= selectors.length * document.querySelectorAll('div.mxgraph').length) {
      observer.disconnect();
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
  hideButtonIfFound();
}