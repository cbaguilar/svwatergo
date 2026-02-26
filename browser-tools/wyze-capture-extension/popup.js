(() => {
  "use strict";

  const statusEl = document.getElementById("status");

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  async function getActiveTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0];
  }

  async function openOverlay() {
    const tab = await getActiveTab();
    if (!tab || !tab.id) throw new Error("No active tab");
    await chrome.tabs.sendMessage(tab.id, { type: "WYZE_SHOW_OVERLAY" });
    setStatus("Overlay opened in page. Use the Wyze Overlay panel to record.");
  }

  async function hideOverlay() {
    const tab = await getActiveTab();
    if (!tab || !tab.id) throw new Error("No active tab");
    await chrome.tabs.sendMessage(tab.id, { type: "WYZE_HIDE_OVERLAY" });
    setStatus("Overlay hidden.");
  }

  async function pingPage() {
    try {
      const tab = await getActiveTab();
      if (!tab || !tab.id) throw new Error("No active tab");
      await chrome.tabs.sendMessage(tab.id, { type: "WYZE_PING" });
      setStatus("Connected. Use 'Open Overlay' to control recording.");
    } catch (e) {
      setStatus("Open a Wyze web page tab first (my.wyze.com/live).");
    }
  }

  function removeIfExists(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function makeButton(id, text, onClick, primary = false) {
    const b = document.createElement("button");
    b.id = id;
    b.textContent = text;
    if (primary) b.className = "primary";
    b.addEventListener("click", () => onClick().catch((e) => setStatus(String(e.message || e))));
    return b;
  }

  function simplifyPopupUI() {
    const wrap = document.querySelector(".wrap");
    if (!wrap) return;

    // Remove old multi-control sections and rebuild a minimal launcher UI.
    wrap.innerHTML = "";

    const header = document.createElement("header");
    header.innerHTML = `<h1>Wyze Capture</h1><div class="sub">Use the in-page Wyze Overlay for all recording controls</div>`;
    wrap.appendChild(header);

    const section = document.createElement("section");
    const row1 = document.createElement("div");
    row1.className = "row";
    row1.appendChild(makeButton("openOverlay", "Open Overlay", openOverlay, true));
    row1.appendChild(makeButton("hideOverlay", "Hide Overlay", hideOverlay));
    section.appendChild(row1);

    const row2 = document.createElement("div");
    row2.className = "row";
    const openOptions = document.createElement("button");
    openOptions.textContent = "Options";
    openOptions.addEventListener("click", () => chrome.runtime.openOptionsPage());
    row2.appendChild(openOptions);
    section.appendChild(row2);

    wrap.appendChild(section);

    const statusSection = document.createElement("section");
    const status = document.createElement("div");
    status.id = "status";
    status.className = "status";
    statusSection.appendChild(status);
    wrap.appendChild(statusSection);
  }

  simplifyPopupUI();
  pingPage();
})();
