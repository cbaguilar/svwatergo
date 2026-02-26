(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const statusEl = $("status");
  const selectedListEl = $("selectedList");
  const streamsListEl = $("streamsList");

  function setStatus(msg) {
    statusEl.textContent = msg;
  }

  async function getActiveTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0];
  }

  async function sendToContent(type, payload) {
    const tab = await getActiveTab();
    if (!tab || !tab.id) throw new Error("No active tab");
    return chrome.tabs.sendMessage(tab.id, { type, ...payload });
  }

  function readNames() {
    const selected = Array.from(streamsListEl.querySelectorAll("input[type='checkbox']:checked"))
      .map((el) => el.value)
      .filter(Boolean);
    if (selected.length) return selected;
    return $("names")
      .value
      .split(/\n/)
      .map((n) => n.trim())
      .filter(Boolean);
  }

  function readCheckedNames() {
    return Array.from(streamsListEl.querySelectorAll("input[type='checkbox']:checked"))
      .map((el) => el.value)
      .filter(Boolean);
  }

  function readConfig() {
    return {
      durationMs: Number($("duration").value || 10000),
      runHours: Number($("runHours").value || 0),
      tag: $("tag").value || "",
      minBytes: Number($("minBytes").value || 0),
      maxRetries: Number($("maxRetries").value || 0),
      uploadEnabled: $("uploadEnabled").checked,
      uploadUrl: $("uploadUrl").value || "",
      useRecorder: $("useRecorder").checked
    };
  }

  async function persistUI() {
    const cfg = readConfig();
    const cached = {
      cfg,
      namesText: $("names").value || "",
      checked: readCheckedNames(),
      streams: Array.from(streamsListEl.querySelectorAll("input[type='checkbox']")).map((el) => el.value)
    };
    await chrome.storage.local.set({ wyzePopupState: cached });
  }

  async function saveDefaults() {
    const cfg = readConfig();
    await chrome.storage.local.set({ wyzeDefaults: cfg });
    setStatus("Defaults saved");
  }

  async function loadDefaults() {
    const { wyzeDefaults } = await chrome.storage.local.get("wyzeDefaults");
    const cfg = wyzeDefaults || {};
    $("duration").value = cfg.durationMs || 10000;
    $("runHours").value = cfg.runHours || 6;
    $("tag").value = cfg.tag || "10s";
    $("minBytes").value = cfg.minBytes || 40960;
    $("maxRetries").value = cfg.maxRetries || 1;
    $("uploadEnabled").checked = !!cfg.uploadEnabled;
    $("uploadUrl").value = cfg.uploadUrl || "";
    $("useRecorder").checked = !!cfg.useRecorder;
    $("uploadEnabled").disabled = !!cfg.useRecorder;
  }

  async function loadPopupState() {
    const { wyzePopupState } = await chrome.storage.local.get("wyzePopupState");
    if (!wyzePopupState) return;
    if (wyzePopupState.namesText) $("names").value = wyzePopupState.namesText;
    if (Array.isArray(wyzePopupState.streams)) {
      const items = wyzePopupState.streams.map((name) => ({ name, hasVideo: false }));
      renderStreams(items, new Set(wyzePopupState.checked || []));
    }
  }

  async function applyUploadSettings() {
    const cfg = readConfig();
    let mode = "download";
    let enabled = cfg.uploadEnabled;
    if (cfg.useRecorder) {
      mode = "extension";
      enabled = false;
    } else if (cfg.uploadEnabled) {
      mode = "upload";
    }
    await sendToContent("WYZE_CMD", { cmd: "setUpload", payload: { mode, enabled, url: cfg.uploadUrl } });
  }

  async function recordSequential() {
    const names = readNames();
    if (!names.length) throw new Error("No camera names provided");
    const cfg = readConfig();
    await applyUploadSettings();
    if (cfg.runHours > 0) {
      const totalMs = cfg.runHours * 60 * 60 * 1000;
      setStatus(`Recording loop for ${cfg.runHours}h across ${names.length} camera(s)...`);
      const res = await sendToContent("WYZE_CMD", {
        cmd: "recordLoop",
        payload: {
          names,
          durationMs: cfg.durationMs,
          totalMs,
          tag: cfg.tag || `${cfg.durationMs}ms`,
          minBytes: cfg.minBytes,
          maxRetries: cfg.maxRetries
        }
      });
      setStatus(`Done: ${res.result.length} recording(s)`);
      return;
    }
    setStatus(`Recording ${names.length} camera(s) sequentially...`);
    const res = await sendToContent("WYZE_CMD", {
      cmd: "recordSequential",
      payload: {
        names,
        durationMs: cfg.durationMs,
        tag: cfg.tag || `${cfg.durationMs}ms`,
        minBytes: cfg.minBytes,
        maxRetries: cfg.maxRetries
      }
    });
    setStatus(`Done: ${res.result.length} recording(s)`);
  }

  async function recordOne() {
    const names = readNames();
    if (!names.length) throw new Error("No camera names provided");
    const cfg = readConfig();
    await applyUploadSettings();
    setStatus(`Recording ${names[0]}...`);
    const res = await sendToContent("WYZE_CMD", {
      cmd: "recordOne",
      payload: {
        name: names[0],
        durationMs: cfg.durationMs,
        tag: cfg.tag || `${cfg.durationMs}ms`,
        minBytes: cfg.minBytes,
        maxRetries: cfg.maxRetries
      }
    });
    setStatus(`Saved: ${res.result.filename}`);
  }

  async function scanCameras() {
    const res = await sendToContent("WYZE_SCAN_DETAILS", {});
    if (res.ok) {
      const names = res.items.map((i) => i.name);
      $("names").value = names.join("\n");
      renderStreams(res.items);
      setStatus(`Found ${res.items.length} camera(s)`);
      await persistUI();
    } else {
      setStatus(res.error || "Scan failed");
    }
  }

  async function getSelection() {
    const res = await sendToContent("WYZE_GET_SELECTION", {});
    if (res.ok) {
      $("names").value = res.names.join("\n");
      setStatus(`Selected ${res.names.length} camera(s)`);
    } else {
      setStatus(res.error || "Selection failed");
    }
  }

  async function refreshSelectedList() {
    try {
      const res = await sendToContent("WYZE_GET_SELECTION", {});
      if (res.ok) {
        selectedListEl.textContent = res.names.join("\n");
      }
    } catch (_) {}
  }

  function renderStreams(items, checkedSet) {
    streamsListEl.innerHTML = "";
    for (const item of items) {
      const row = document.createElement("label");
      row.className = "stream-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = item.name;
      if (checkedSet && checkedSet.has(item.name)) cb.checked = true;
      cb.addEventListener("change", () => persistUI().catch(() => {}));
      const name = document.createElement("span");
      name.textContent = item.name;
      const meta = document.createElement("span");
      meta.className = "stream-meta";
      if (item.hasVideo) {
        meta.textContent = `${item.videoWidth || 0}x${item.videoHeight || 0} rs=${item.readyState} muted=${item.muted ? "1" : "0"} paused=${item.paused ? "1" : "0"}`;
      } else {
        meta.textContent = "no-video";
      }
      row.appendChild(cb);
      row.appendChild(name);
      row.appendChild(meta);
      streamsListEl.appendChild(row);
    }
  }

  async function stopAll() {
    await sendToContent("WYZE_CMD", { cmd: "stopAll", payload: {} });
    setStatus("Stopped");
  }

  $("scan").addEventListener("click", () => scanCameras().catch((e) => setStatus(String(e.message || e))));
  $("getSelection").addEventListener("click", () => getSelection().catch((e) => setStatus(String(e.message || e))));
  $("recordSequential").addEventListener("click", () => recordSequential().catch((e) => setStatus(String(e.message || e))));
  $("recordOne").addEventListener("click", () => recordOne().catch((e) => setStatus(String(e.message || e))));
  $("stopAll").addEventListener("click", () => stopAll().catch((e) => setStatus(String(e.message || e))));
  $("saveDefaults").addEventListener("click", () => saveDefaults().catch((e) => setStatus(String(e.message || e))));
  $("openRecorder").addEventListener("click", async () => {
    const url = chrome.runtime.getURL("record.html");
    await chrome.tabs.create({ url });
  });

  $("useRecorder").addEventListener("change", () => {
    const on = $("useRecorder").checked;
    $("uploadEnabled").disabled = on;
    if (on) $("uploadEnabled").checked = false;
    persistUI().catch(() => {});
  });
  $("names").addEventListener("input", () => persistUI().catch(() => {}));
  $("duration").addEventListener("input", () => persistUI().catch(() => {}));
  $("runHours").addEventListener("input", () => persistUI().catch(() => {}));
  $("tag").addEventListener("input", () => persistUI().catch(() => {}));
  $("minBytes").addEventListener("input", () => persistUI().catch(() => {}));
  $("maxRetries").addEventListener("input", () => persistUI().catch(() => {}));
  $("uploadEnabled").addEventListener("change", () => persistUI().catch(() => {}));
  $("uploadUrl").addEventListener("input", () => persistUI().catch(() => {}));

  loadDefaults().catch(() => {});
  loadPopupState().catch(() => {});
  refreshSelectedList();
  setInterval(refreshSelectedList, 2000);
})();
