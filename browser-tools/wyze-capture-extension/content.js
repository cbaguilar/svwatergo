(() => {
  "use strict";

  const injectedId = "wyze-rtc-injected";
  const pending = new Map();

  function log(...args) {
    try {
      console.log("[wyze-ext]", ...args);
    } catch (_) {}
  }

  function inject() {
    if (document.getElementById(injectedId)) return;
    const s = document.createElement("script");
    s.id = injectedId;
    s.src = chrome.runtime.getURL("injected.js");
    s.type = "text/javascript";
    s.onload = () => {
      s.remove();
      log("injected script loaded");
    };
    (document.head || document.documentElement).appendChild(s);
  }

  function sendToPage(cmd, payload) {
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const msg = { source: "wyze-ext", type: "WYZE_EXT_CMD", cmd, payload, requestId };
    const p = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(requestId);
        reject(new Error(`Timeout waiting for ${cmd}`));
      }, 15000);
      pending.set(requestId, { resolve, reject, timer });
    });
    window.postMessage(msg, "*");
    return p;
  }

  const OVERLAY_ID = "wyze-overlay-root";

  function buildOverlay() {
    if (document.getElementById(OVERLAY_ID)) return;
    const host = document.createElement("div");
    host.id = OVERLAY_ID;
    host.style.position = "fixed";
    host.style.top = "12px";
    host.style.right = "12px";
    host.style.zIndex = "999999";
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        .panel { width: 360px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.12); font-family: "SF Pro Text","Segoe UI","Helvetica Neue",Arial,sans-serif; font-size: 12px; color: #111; }
        .hdr { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid #e5e7eb; background: #f5f6f8; border-radius: 8px 8px 0 0; }
        .title { font-weight: 600; }
        .btn { border: 1px solid #d0d7de; background: #fff; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px; }
        .btn.primary { background: #1f6feb; color: #fff; border-color: #1f6feb; }
        .body { padding: 8px 10px; display: flex; flex-direction: column; gap: 8px; }
        .row { display: flex; gap: 6px; align-items: center; }
        .row label { width: 90px; }
        input[type="text"], input[type="number"], textarea { flex: 1; border: 1px solid #d0d7de; border-radius: 6px; padding: 4px 6px; font-size: 12px; }
        textarea { height: 70px; }
        .list { max-height: 140px; overflow: auto; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 6px; background: #fafafa; }
        .item { display: flex; gap: 6px; align-items: center; padding: 2px 0; }
        .meta { margin-left: auto; color: #555; font-size: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
        .status { font-size: 11px; color: #333; min-height: 14px; }
      </style>
      <div class="panel">
        <div class="hdr">
          <div class="title">Wyze Overlay</div>
          <button class="btn" id="toggle">Hide</button>
        </div>
        <div class="body" id="body">
          <div class="row">
            <button class="btn" id="scan">Scan Cameras</button>
            <button class="btn" id="getSel">Get Selection</button>
          </div>
          <div class="row">
            <label>Streams</label>
          </div>
          <div class="list" id="streams"></div>
          <div class="row">
            <label>Names</label>
          </div>
          <textarea id="names" placeholder="Camera names (one per line)"></textarea>

          <div class="row"><label>Duration</label><input id="duration" type="number" min="1000" step="1000"/></div>
          <div class="row"><label>Run hours</label><input id="runHours" type="number" min="0" step="0.5"/></div>
          <div class="row"><label>Tag</label><input id="tag" type="text" placeholder="10s"/></div>
          <div class="row"><label>Min bytes</label><input id="minBytes" type="number" min="0" step="1024"/></div>
          <div class="row"><label>Max retries</label><input id="maxRetries" type="number" min="0" step="1"/></div>

          <div class="row">
            <label><input id="uploadEnabled" type="checkbox" /> Upload</label>
            <input id="uploadUrl" type="text" placeholder="https://your-server/upload"/>
          </div>
          <div class="row">
            <label><input id="useRecorder" type="checkbox" /> Save to picked folder</label>
            <button class="btn" id="pickFolder">Pick Folder</button>
            <button class="btn" id="clearFolder">Clear</button>
          </div>
          <div class="status" id="folderStatus"></div>

          <div class="row">
            <button class="btn primary" id="recordSeq">Record Sequential</button>
            <button class="btn" id="recordOne">Record First</button>
            <button class="btn" id="stopAll">Stop</button>
          </div>
          <div class="status" id="status"></div>
        </div>
      </div>
    `;
    document.documentElement.appendChild(host);
    wireOverlay(shadow);
  }

  function wireOverlay(shadow) {
    const $ = (id) => shadow.getElementById(id);
    const streamsEl = $("streams");
    const statusEl = $("status");
    const folderStatusEl = $("folderStatus");

    const setStatus = (msg) => { statusEl.textContent = msg; };
    const setFolderStatus = (msg) => { folderStatusEl.textContent = msg; };

    const readCheckedNames = () =>
      Array.from(streamsEl.querySelectorAll("input[type='checkbox']:checked"))
        .map((el) => el.value)
        .filter(Boolean);

    const readNames = () => {
      const selected = readCheckedNames();
      if (selected.length) return selected;
      return ($("names").value || "").split(/\n/).map((n) => n.trim()).filter(Boolean);
    };

    const readConfig = () => ({
      durationMs: Number($("duration").value || 10000),
      runHours: Number($("runHours").value || 0),
      tag: $("tag").value || "",
      minBytes: Number($("minBytes").value || 0),
      maxRetries: Number($("maxRetries").value || 0),
      uploadEnabled: $("uploadEnabled").checked,
      uploadUrl: $("uploadUrl").value || "",
      useRecorder: $("useRecorder").checked
    });

    const persistUI = async () => {
      const cfg = readConfig();
      const cached = {
        cfg,
        namesText: $("names").value || "",
        checked: readCheckedNames(),
        streams: Array.from(streamsEl.querySelectorAll("input[type='checkbox']")).map((el) => el.value)
      };
      await chrome.storage.local.set({ wyzeOverlayState: cached });
    };

    const loadDefaults = async () => {
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
    };

    const loadOverlayState = async () => {
      const { wyzeOverlayState } = await chrome.storage.local.get("wyzeOverlayState");
      if (!wyzeOverlayState) return;
      if (wyzeOverlayState.namesText) $("names").value = wyzeOverlayState.namesText;
      if (Array.isArray(wyzeOverlayState.streams)) {
        const items = wyzeOverlayState.streams.map((name) => ({ name, hasVideo: false }));
        renderStreams(items, new Set(wyzeOverlayState.checked || []));
      }
    };

    const applyUploadSettings = async () => {
      const cfg = readConfig();
      let mode = "download";
      let enabled = cfg.uploadEnabled;
      if (cfg.useRecorder) {
        mode = "page";
        enabled = false;
      } else if (cfg.uploadEnabled) {
        mode = "upload";
      }
      await sendToPage("setUpload", { mode, enabled, url: cfg.uploadUrl });
    };

    const renderStreams = (items, checkedSet) => {
      streamsEl.innerHTML = "";
      for (const item of items) {
        const row = document.createElement("label");
        row.className = "item";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.value = item.name;
        if (checkedSet && checkedSet.has(item.name)) cb.checked = true;
        cb.addEventListener("change", () => persistUI().catch(() => {}));
        const name = document.createElement("span");
        name.textContent = item.name;
        const meta = document.createElement("span");
        meta.className = "meta";
        if (item.hasVideo) {
          meta.textContent = `${item.videoWidth || 0}x${item.videoHeight || 0} rs=${item.readyState} muted=${item.muted ? "1" : "0"} paused=${item.paused ? "1" : "0"}`;
        } else {
          meta.textContent = "no-video";
        }
        row.appendChild(cb);
        row.appendChild(name);
        row.appendChild(meta);
        streamsEl.appendChild(row);
      }
    };

    $("scan").addEventListener("click", async () => {
      try {
        const items = scanCameraDetails();
        const names = items.map((i) => i.name);
        $("names").value = names.join("\n");
        renderStreams(items);
        setStatus(`Found ${items.length} camera(s)`);
        await persistUI();
      } catch (e) {
        setStatus(String(e.message || e));
      }
    });

    $("getSel").addEventListener("click", async () => {
      const names = await getSelection();
      $("names").value = names.join("\n");
      setStatus(`Selected ${names.length} camera(s)`);
      await persistUI();
    });

    $("recordSeq").addEventListener("click", async () => {
      try {
        const names = readNames();
        if (!names.length) throw new Error("No camera names provided");
        const cfg = readConfig();
        await applyUploadSettings();
        if (cfg.runHours > 0) {
          const totalMs = cfg.runHours * 60 * 60 * 1000;
          setStatus(`Recording loop for ${cfg.runHours}h across ${names.length} camera(s)...`);
          const res = await sendToPage("recordLoop", {
            names,
            durationMs: cfg.durationMs,
            totalMs,
            tag: cfg.tag || `${cfg.durationMs}ms`,
            minBytes: cfg.minBytes,
            maxRetries: cfg.maxRetries
          });
          setStatus(`Done: ${(res || []).length} recording(s)`);
        } else {
          setStatus(`Recording ${names.length} camera(s) sequentially...`);
          const res = await sendToPage("recordSequential", {
            names,
            durationMs: cfg.durationMs,
            tag: cfg.tag || `${cfg.durationMs}ms`,
            minBytes: cfg.minBytes,
            maxRetries: cfg.maxRetries
          });
          setStatus(`Done: ${(res || []).length} recording(s)`);
        }
      } catch (e) {
        setStatus(String(e.message || e));
      }
    });

    $("recordOne").addEventListener("click", async () => {
      try {
        const names = readNames();
        if (!names.length) throw new Error("No camera names provided");
        const cfg = readConfig();
        await applyUploadSettings();
        setStatus(`Recording ${names[0]}...`);
        const res = await sendToPage("recordOne", {
          name: names[0],
          durationMs: cfg.durationMs,
          tag: cfg.tag || `${cfg.durationMs}ms`,
          minBytes: cfg.minBytes,
          maxRetries: cfg.maxRetries
        });
        setStatus(`Saved: ${res && res.filename ? res.filename : ""}`);
      } catch (e) {
        setStatus(String(e.message || e));
      }
    });

    $("stopAll").addEventListener("click", async () => {
      try {
        await sendToPage("stopAll", {});
        setStatus("Stopped");
      } catch (e) {
        setStatus(String(e.message || e));
      }
    });

    $("pickFolder").addEventListener("click", async () => {
      try {
        const res = await sendToPage("pickDir", {});
        setFolderStatus(res && res.status ? res.status : "Folder selected");
      } catch (e) {
        setFolderStatus(String(e.message || e));
      }
    });

    $("clearFolder").addEventListener("click", async () => {
      try {
        const res = await sendToPage("clearDir", {});
        setFolderStatus(res && res.status ? res.status : "Folder cleared");
      } catch (e) {
        setFolderStatus(String(e.message || e));
      }
    });

    $("useRecorder").addEventListener("change", () => {
      const on = $("useRecorder").checked;
      $("uploadEnabled").disabled = on;
      if (on) $("uploadEnabled").checked = false;
      persistUI().catch(() => {});
    });

    const inputs = ["names", "duration", "runHours", "tag", "minBytes", "maxRetries", "uploadEnabled", "uploadUrl"];
    for (const id of inputs) {
      $(id).addEventListener(id === "uploadEnabled" ? "change" : "input", () => persistUI().catch(() => {}));
    }

    $("toggle").addEventListener("click", () => {
      const body = shadow.getElementById("body");
      const hidden = body.style.display === "none";
      body.style.display = hidden ? "block" : "none";
      $("toggle").textContent = hidden ? "Hide" : "Show";
    });

    loadDefaults().catch(() => {});
    loadOverlayState().catch(() => {});
    sendToPage("dirStatus", {}).then((res) => {
      setFolderStatus(res && res.status ? res.status : "Folder status unknown");
    }).catch(() => {
      setFolderStatus("Folder status unknown");
    });
  }

  window.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.source !== "wyze-ext" || data.type !== "WYZE_EXT_EVENT") return;
    const { requestId, ok, result, error } = data;
    if (!requestId || !pending.has(requestId)) return;
    const entry = pending.get(requestId);
    clearTimeout(entry.timer);
    pending.delete(requestId);
    if (ok) entry.resolve(result);
    else entry.reject(new Error(error || "Unknown error"));
  });


  function enableSelectionMode() {
    if (window.__wyzeSelectionMode) return;
    window.__wyzeSelectionMode = true;
    document.addEventListener(
      "click",
      (e) => {
        if (!window.__wyzeSelectionMode) return;
        if (!e.altKey && !e.ctrlKey) return;
        const target = e.target;
        if (!target) return;
        const container = findCameraContainer(target);
        if (!container) return;
        e.preventDefault();
        e.stopPropagation();
        toggleSelected(container);
      },
      true
    );
    log("selection mode enabled: Alt-click or Ctrl-click camera card");
  }

  async function handleContextRecord(e) {
    const target = e.target;
    if (!target) return;
    const container = findCameraContainer(target);
    if (!container) return;
    const name = extractCameraName(container);
    if (!name) return;
    e.preventDefault();
    e.stopPropagation();
    try {
      const { wyzeDefaults } = await chrome.storage.local.get("wyzeDefaults");
      const cfg = wyzeDefaults || {};
      const durationMs = Number(cfg.durationMs || 10000);
      const tag = cfg.tag || `${durationMs}ms`;
      const minBytes = Number(cfg.minBytes || 0);
      const maxRetries = Number(cfg.maxRetries || 0);
      let mode = "download";
      let enabled = !!cfg.uploadEnabled;
      if (cfg.useRecorder) {
        mode = "page";
        enabled = false;
      } else if (cfg.uploadEnabled) {
        mode = "upload";
      }
      await sendToPage("setUpload", { mode, enabled, url: cfg.uploadUrl || "" });
      await sendToPage("recordOne", { name, durationMs, tag, minBytes, maxRetries });
      log("context record complete", { name });
    } catch (err) {
      log("context record failed", { name, err: String(err && err.message ? err.message : err) });
    }
  }

  function findCameraContainer(node) {
    let el = node;
    for (let i = 0; i < 8 && el; i++) {
      if (el.matches && el.matches("li.MuiImageListItem-root")) return el;
      if (el.querySelector && el.querySelector("video")) return el;
      el = el.parentElement;
    }
    return null;
  }

  function toggleSelected(container) {
    const selected = container.dataset.wyzeSelected === "1";
    if (selected) {
      container.dataset.wyzeSelected = "0";
      container.style.outline = "";
    } else {
      container.dataset.wyzeSelected = "1";
      container.style.outline = "3px solid #1f6feb";
      container.style.outlineOffset = "2px";
    }
  }

  async function getSelection() {
    const nodes = Array.from(document.querySelectorAll("[data-wyze-selected='1']"));
    const names = nodes.map((n) => extractCameraName(n)).filter(Boolean);
    return Array.from(new Set(names));
  }

  function extractCameraName(container) {
    if (!container) return null;
    const titleEl = container.querySelector("p.MuiTypography-root.MuiTypography-body2");
    if (titleEl && titleEl.textContent) return titleEl.textContent.trim();
    const text = (container.textContent || "").replace(/\s+/g, " ").trim();
    if (!text) return null;
    const banned = ["LIVE", "Device Offline", "cam-unlimited", "Please check your Internet", "try to reboot"];
    const parts = text
      .split(/\n|\r|\t/)
      .map((p) => p.trim())
      .filter(Boolean);
    for (const part of parts) {
      if (banned.some((b) => part.includes(b))) continue;
      if (part.length < 2) continue;
      return part;
    }
    return parts.length ? parts[0] : null;
  }

  function scanCamerasFromDom() {
    const candidates = new Set();
    const cards = Array.from(document.querySelectorAll("li.MuiImageListItem-root"));
    for (const card of cards) candidates.add(card);
    const names = [];
    for (const c of candidates) {
      if (!c || !c.textContent) continue;
      const name = extractCameraName(c);
      if (name) names.push(name);
    }
    return Array.from(new Set(names));
  }

  function scanCameraDetails() {
    const cards = Array.from(document.querySelectorAll("li.MuiImageListItem-root"));
    const out = [];
    for (const card of cards) {
      const name = extractCameraName(card);
      if (!name) continue;
      const video = card.querySelector("video");
      const meta = video
        ? {
            hasVideo: true,
            readyState: video.readyState,
            videoWidth: video.videoWidth,
            videoHeight: video.videoHeight,
            muted: video.muted,
            paused: video.paused
          }
        : { hasVideo: false };
      out.push({ name, ...meta });
    }
    return out;
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    (async () => {
      if (!msg || !msg.type) return;
      if (msg.type === "WYZE_ENABLE_SELECTION") {
        enableSelectionMode();
        sendResponse({ ok: true });
        return;
      }
      if (msg.type === "WYZE_GET_SELECTION") {
        const names = await getSelection();
        sendResponse({ ok: true, names });
        return;
      }
      if (msg.type === "WYZE_SCAN_CAMERAS") {
        const names = scanCamerasFromDom();
        sendResponse({ ok: true, names });
        return;
      }
      if (msg.type === "WYZE_SCAN_DETAILS") {
        const items = scanCameraDetails();
        sendResponse({ ok: true, items });
        return;
      }
      if (msg.type === "WYZE_CMD") {
        const result = await sendToPage(msg.cmd, msg.payload || {});
        sendResponse({ ok: true, result });
        return;
      }
    })().catch((err) => {
      sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
    });
    return true;
  });

  inject();
  enableSelectionMode();
  buildOverlay();
  document.addEventListener("contextmenu", handleContextRecord, true);
})();
