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
    document.querySelectorAll(".mxgraph").forEach(container => {
      try {
        const config = JSON.parse(container.getAttribute("data-mxgraph") || "{}");

        // 🛑 Skip if viewer-on-click (i.e., diagram is hidden and wrapped in popup mode)
        const style = container.getAttribute("style") || "";
        const isHiddenPopup = style.includes("display:none") && style.includes("height:0");

        if (isHiddenPopup) {
          return; // 🧼 Don't inject the floating edit button in caption-only mode
        }

        // ✅ Only add button if edit is configured and toolbar includes edit
        if (!(config.edit && config.toolbar?.includes("edit"))) return;

        const wrapper = container.closest(".drawio-container");
        if (!wrapper || wrapper.querySelector(".drawio-floating-edit")) return;

        const btn = document.createElement("a");
        btn.className = "drawio-floating-edit";
        btn.href = config.edit;
        btn.target = "_blank";
        btn.title = "Edit this diagram";
        btn.setAttribute("aria-label", "Edit this diagram");
        btn.setAttribute("role", "button");

        btn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path fill="currentColor" d="M10 20H6V4h7v5h5v3.1l2-2V8l-6-6H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h4zm10.2-7c.1 0 .3.1.4.2l1.3 1.3c.2.2.2.6 0 .8l-1 1-2.1-2.1 1-1c.1-.1.2-.2.4-.2m0 3.9L14.1 23H12v-2.1l6.1-6.1z"/>
          </svg>
        `;
        wrapper.appendChild(btn);
      } catch (err) {
        console.warn("[drawio.js] ⚠️ Failed to inject floating edit button:", err);
      }
    });
  });
})();

(function waitForDrawioReady(attempts = 0) {
  if (typeof GraphViewer !== "undefined" && typeof document$?.subscribe === "function") {
    document$.subscribe(() => {
      GraphViewer.processElements();
      hideExportPrintButtons();
      bindAllCaptionLinks();
    });
  } else if (attempts < 50) {
    setTimeout(() => waitForDrawioReady(attempts + 1), 200);
  } else {
    console.warn("[drawio.js] ❌ Timeout: Drawio viewer not ready after 50 attempts");
  }
})();

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

function handleCaptionClick(containerId) {
  const container = document.getElementById(containerId);
  const original = container?.querySelector(".mxgraph");
  if (!original) return;

  document.querySelectorAll(".drawio-popup-overlay").forEach(el => el.remove());

  const overlay = document.createElement("div");
  overlay.className = "drawio-popup-overlay";
  overlay.style.cssText = `
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 900;
    display: flex;
    justify-content: center;
    align-items: center;
  `;

  const popup = document.createElement("div");
  popup.className = "drawio-popup";
  popup.style.cssText = `
    position: relative;
    width: 90vw;
    height: 90vh;
    background: white;
    border-radius: 8px;
    padding: 1em;
    box-shadow: 0 0 12px rgba(0,0,0,0.4);
    overflow: auto;
    z-index: 901;
  `;

  const close = document.createElement("button");
  close.innerHTML = "&times;";
  close.title = "Close";
  close.setAttribute("aria-label", "Close popup");
  close.className = "drawio-popup-close";
  close.onclick = (e) => {
    e.stopPropagation();
    overlay.remove();
  };

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  function escHandler(e) {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", escHandler);
    }
  }
  document.addEventListener("keydown", escHandler);

  const copy = original.cloneNode(true);
  copy.removeAttribute("id");
  copy.style.visibility = "visible";
  copy.style.height = "100%";
  copy.style.overflow = "visible";
  copy.style.display = "block";

  const config = JSON.parse(copy.getAttribute("data-mxgraph") || '{}');
  config.toolbar = "pages zoom layers edit";
  config["toolbar-nohide"] = true;
  config["lightbox"] = false;
  copy.setAttribute("data-mxgraph", JSON.stringify(config));

  popup.appendChild(close);
  popup.appendChild(copy);

  // ✅ Inject Edit icon into popup if config.edit is present
  if (typeof config.edit === "string" && config.edit !== "_blank") {
    const editBtn = document.createElement("a");
    editBtn.href = config.edit;
    editBtn.target = "_blank";
    editBtn.className = "drawio-floating-edit";
    editBtn.title = "Edit this diagram";
    editBtn.setAttribute("aria-label", "Edit this diagram");

    editBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="currentColor" d="M10 20H6V4h7v5h5v3.1l2-2V8l-6-6H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h4zm10.2-7c.1 0 .3.1.4.2l1.3 1.3c.2.2.2.6 0 .8l-1 1-2.1-2.1 1-1c.1-.1.2-.2.4-.2m0 3.9L14.1 23H12v-2.1l6.1-6.1z"/>
      </svg>
    `;

    popup.insertBefore(editBtn, popup.firstChild);
  }

  overlay.appendChild(popup);
  document.body.appendChild(overlay);

  setTimeout(() => {
    const newViewer = overlay.querySelector(".mxgraph");
    if (newViewer && typeof GraphViewer !== "undefined") {
      GraphViewer.processElements();
    }
  }, 0);
}

function bindCaptionLink(link) {
  if (link.dataset.bound === "true") return;

  const containerId = link.getAttribute("data-lightbox-id");
  if (!containerId) return;

  console.log("🧪 Binding caption link to container:", containerId);

  link.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    handleCaptionClick(containerId);
  });

  link.dataset.bound = "true";
}

function bindAllCaptionLinks() {
  document.querySelectorAll("a[data-lightbox-id], span[data-lightbox-id]").forEach(bindCaptionLink);
}

document.addEventListener("DOMContentLoaded", () => {
  bindAllCaptionLinks();
  new MutationObserver(bindAllCaptionLinks).observe(document.body, {
    childList: true,
    subtree: true,
  });
});
