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