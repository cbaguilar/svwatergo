(() => {
  "use strict";

  if (window.__wyzeRTCInjected) return;
  window.__wyzeRTCInjected = true;

  const state = {
    pcs: [],
    audioTracks: [],
    logs: [],
    uploads: {
      enabled: false,
      url: "",
      mode: "download"
    }
  };

  const DB_NAME = "wyze-recorder";
  const STORE = "handles";
  let dirHandle = null;

  function log(...args) {
    const row = { ts: new Date().toISOString(), args };
    state.logs.push(row);
    try {
      console.log("[wyze-rtc]", ...args);
    } catch (_) {}
  }

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function saveHandle(handle) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(handle, "dir");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function loadHandle() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get("dir");
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  }

  async function clearHandle() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete("dir");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function ensurePermission(handle) {
    if (!handle) return false;
    const perm = await handle.queryPermission({ mode: "readwrite" });
    if (perm === "granted") return true;
    const req = await handle.requestPermission({ mode: "readwrite" });
    return req === "granted";
  }

  async function pickDir() {
    const handle = await window.showDirectoryPicker();
    const ok = await ensurePermission(handle);
    if (!ok) throw new Error("Permission denied");
    dirHandle = handle;
    await saveHandle(handle);
    return { status: "Folder selected" };
  }

  async function dirStatus() {
    if (!dirHandle) {
      dirHandle = await loadHandle();
    }
    if (!dirHandle) return { status: "No folder selected" };
    const ok = await ensurePermission(dirHandle);
    return { status: ok ? "Folder ready" : "Folder needs permission" };
  }

  async function clearDir() {
    dirHandle = null;
    await clearHandle();
    return { status: "Folder cleared" };
  }

  function safeName(name) {
    return String(name || "unknown").replace(/[^a-z0-9-_]+/gi, "_");
  }

  function dateStampUtc(ts) {
    const d = new Date(ts);
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  async function saveToDir({ blob, filename, name, startedAt }) {
    if (!dirHandle) {
      dirHandle = await loadHandle();
    }
    if (!dirHandle) throw new Error("No folder selected");
    const ok = await ensurePermission(dirHandle);
    if (!ok) throw new Error("Permission denied");
    const camDir = await dirHandle.getDirectoryHandle(`camera=${safeName(name)}`, { create: true });
    const dateDir = await camDir.getDirectoryHandle(`date=${dateStampUtc(startedAt)}`, { create: true });
    const fileHandle = await dateDir.getFileHandle(filename, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(blob);
    await writable.close();
  }

  function rememberAudioTrack(track, meta) {
    if (!track || track.kind !== "audio") return;
    const exists = state.audioTracks.some((x) => x.track && x.track.id === track.id);
    if (exists) return;
    state.audioTracks.push({ track, ...meta, firstSeen: new Date().toISOString() });
    window.__wyzeLastRemoteAudioTrack = track;
    log("audio track", { id: track.id, label: track.label, muted: track.muted, ...meta });
  }

  function scanReceivers(pc, pcId, source) {
    try {
      for (const r of pc.getReceivers?.() || []) {
        if (r.track) rememberAudioTrack(r.track, { pcId, source });
      }
    } catch (_) {}
  }

  function findCameraElementByName(name) {
    const needle = name.trim().toLowerCase();
    const titles = Array.from(document.querySelectorAll("li.MuiImageListItem-root p.MuiTypography-root.MuiTypography-body2"));
    for (const el of titles) {
      if (!el || !el.textContent) continue;
      const txt = el.textContent.trim().toLowerCase();
      if (txt === needle || txt.includes(needle)) {
        const container = findContainerWithVideo(el);
        if (container) return container;
      }
    }
    return null;
  }

  function findContainerWithVideo(el) {
    let cur = el;
    for (let i = 0; i < 10 && cur; i++) {
      if (cur.querySelector && cur.querySelector("video")) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  function getVideoFromContainer(container) {
    if (!container) return null;
    const video = container.querySelector("video");
    return video || null;
  }

  function getStreamForCamera(name) {
    const container = findCameraElementByName(name);
    if (!container) throw new Error(`Camera not found: ${name}`);
    const video = getVideoFromContainer(container);
    if (!video) throw new Error(`No video element for camera: ${name}`);
    if (typeof video.captureStream !== "function") {
      throw new Error("captureStream() not available on video element");
    }
    const stream = video.captureStream();
    if (!stream) throw new Error(`captureStream() returned null for: ${name}`);
    return stream;
  }

  function getAudioStreamForCamera(name) {
    const stream = getStreamForCamera(name);
    const audioTracks = stream.getAudioTracks();
    if (!audioTracks || !audioTracks.length) {
      throw new Error(`No audio tracks for camera: ${name}`);
    }
    return new MediaStream(audioTracks);
  }

  function chooseAudioMime() {
    const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
    for (const mt of cands) {
      try {
        if (MediaRecorder.isTypeSupported(mt)) return mt;
      } catch (_) {}
    }
    return "";
  }

  function formatTs(ts) {
    return new Date(ts).toISOString().replace(/[:.]/g, "-");
  }

  async function recordStream({ name, durationMs, tag, minBytes, maxRetries }) {
    const attemptOnce = () => new Promise((resolve, reject) => {
      const stream = getAudioStreamForCamera(name);
      const mime = chooseAudioMime();
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks = [];
      const startedAt = Date.now();
      const ext = /ogg/.test(rec.mimeType) ? "ogg" : "webm";
      const safeName = name.replace(/[^a-z0-9-_]+/gi, "_");
      const filename = `${safeName}__${formatTs(startedAt)}__${tag || `${durationMs}ms`}.${ext}`;

      rec.ondataavailable = (e) => {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      rec.onerror = (e) => {
        reject(e.error || new Error("MediaRecorder error"));
      };
      rec.onstop = async () => {
        const blob = new Blob(chunks, { type: rec.mimeType || "application/octet-stream" });
        if (minBytes && blob.size < minBytes) {
          log("recording too small", { name, bytes: blob.size, minBytes });
          resolve({ tooSmall: true, bytes: blob.size, startedAt });
          return;
        }
        try {
          await saveOrUpload({ blob, filename, name, startedAt, durationMs });
          resolve({ name, bytes: blob.size, type: blob.type, filename, startedAt });
        } catch (err) {
          reject(err);
        }
      };

      rec.start(1000);
      log("recording started (audio)", { name, durationMs, mime: rec.mimeType || mime || "" });
      if (durationMs > 0) setTimeout(() => { try { rec.stop(); } catch (_) {} }, durationMs);
    });

    const retries = Number(maxRetries || 0);
    for (let i = 0; i <= retries; i++) {
      const res = await attemptOnce();
      if (!res.tooSmall) return res;
      log("retrying", { name, attempt: i + 1, maxRetries: retries });
    }
    throw new Error(`Recording too small after ${retries + 1} attempt(s): ${name}`);
  }

  async function saveOrUpload({ blob, filename, name, startedAt, durationMs }) {
    if (state.uploads.mode === "page") {
      await saveToDir({ blob, filename, name, startedAt });
      log("saved to folder", { name, filename, bytes: blob.size });
      return;
    }
    if (state.uploads.enabled && state.uploads.url) {
      const fd = new FormData();
      fd.append("file", blob, filename);
      fd.append("cameraName", name);
      fd.append("startedAt", String(startedAt));
      fd.append("durationMs", String(durationMs));
      const res = await fetch(state.uploads.url, { method: "POST", body: fd });
      if (!res.ok) {
        throw new Error(`Upload failed ${res.status}`);
      }
      log("uploaded", { name, filename, status: res.status });
      return;
    }

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    log("saved", { name, filename, bytes: blob.size, type: blob.type });
  }

  async function recordSequential({ names, durationMs, tag, minBytes, maxRetries }) {
    const out = [];
    const startedAt = Date.now();
    for (const name of names) {
      const res = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
      out.push(res);
      if (window.__wyzeRecordProgressCb) {
        let totalBytes = 0;
        for (const r of out) totalBytes += Number(r && r.bytes ? r.bytes : 0);
        window.__wyzeRecordProgressCb({
          mode: "sequential",
          completed: out.length,
          totalPlanned: names.length,
          currentName: name,
          lastBytes: Number(res && res.bytes ? res.bytes : 0),
          totalBytes,
          elapsedMs: Date.now() - startedAt
        });
      }
    }
    return out;
  }

  async function recordLoop({ names, durationMs, totalMs, tag, minBytes, maxRetries }) {
    const out = [];
    if (!names || !names.length) return out;
    const start = Date.now();
    let idx = 0;
    while (Date.now() - start < totalMs) {
      const name = names[idx % names.length];
      const res = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
      out.push(res);
      if (window.__wyzeRecordProgressCb) {
        let totalBytes = 0;
        for (const r of out) totalBytes += Number(r && r.bytes ? r.bytes : 0);
        window.__wyzeRecordProgressCb({
          mode: "loop",
          completed: out.length,
          totalPlanned: null,
          currentName: name,
          lastBytes: Number(res && res.bytes ? res.bytes : 0),
          totalBytes,
          elapsedMs: Date.now() - start,
          totalMs
        });
      }
      idx += 1;
    }
    return out;
  }

  function stopAll() {
    try {
      if (window.__wyzeAudioRecorder && window.__wyzeAudioRecorder.state !== "inactive") {
        window.__wyzeAudioRecorder.stop();
      }
    } catch (_) {}
  }

  function installHooks() {
    log("injected loaded", location.href);

    const origFetch = window.fetch;
    window.fetch = async function (...args) {
      const res = await origFetch.apply(this, args);
      try {
        const url = String(args[0]?.url || args[0] || "");
        const ct = res.headers?.get?.("content-type") || "";
        if (/get-streams|webrtc|kinesis|signal|ice|turn/i.test(url)) {
          const txt = await res.clone().text();
          log("fetch", { url, status: res.status, ct, bodyPreview: txt.slice(0, 2000) });
        }
      } catch (_) {}
      return res;
    };

    const xo = XMLHttpRequest.prototype.open;
    const xs = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__wyzeMeta = { method, url };
      return xo.call(this, method, url, ...rest);
    };
    XMLHttpRequest.prototype.send = function (body) {
      this.addEventListener("load", function () {
        try {
          const url = String(this.__wyzeMeta?.url || "");
          if (/get-streams|webrtc|kinesis|signal|ice|turn/i.test(url)) {
            const txt = typeof this.responseText === "string" ? this.responseText : "";
            log("xhr", { ...this.__wyzeMeta, status: this.status, bodyPreview: txt.slice(0, 2000) });
          }
        } catch (_) {}
      });
      return xs.call(this, body);
    };

    const NativePC = window.RTCPeerConnection;
    if (!NativePC) {
      log("RTCPeerConnection missing in top frame");
      return;
    }

    function WrappedPC(...args) {
      const pc = new NativePC(...args);
      const pcId = state.pcs.push(pc) - 1;
      pc.__wyzePcId = pcId;
      log("pc created", { pcId, config: args[0] });

      pc.addEventListener("track", (e) => {
        log("pc track", {
          pcId,
          kind: e.track?.kind,
          id: e.track?.id,
          label: e.track?.label,
          streams: (e.streams || []).map((s) => s.id)
        });
        rememberAudioTrack(e.track, { pcId, source: "track-event" });
      });

      pc.addEventListener("icecandidate", (e) => {
        log("icecandidate", { pcId, candidate: e.candidate?.candidate || null });
      });
      pc.addEventListener("iceconnectionstatechange", () => {
        log("ice state", { pcId, state: pc.iceConnectionState });
      });
      pc.addEventListener("connectionstatechange", () => {
        log("pc state", { pcId, state: pc.connectionState });
      });

      const _setRemoteDescription = pc.setRemoteDescription.bind(pc);
      pc.setRemoteDescription = async function (desc) {
        log("setRemoteDescription", { pcId, type: desc?.type, sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        const out = await _setRemoteDescription(desc);
        setTimeout(() => scanReceivers(pc, pcId, "post-remote-desc-500ms"), 500);
        setTimeout(() => scanReceivers(pc, pcId, "post-remote-desc-2000ms"), 2000);
        return out;
      };

      const _setLocalDescription = pc.setLocalDescription.bind(pc);
      pc.setLocalDescription = async function (desc) {
        log("setLocalDescription", { pcId, type: desc?.type, sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        return _setLocalDescription(desc);
      };

      const _addIceCandidate = pc.addIceCandidate.bind(pc);
      pc.addIceCandidate = async function (cand) {
        log("addIceCandidate", { pcId, candidate: cand?.candidate || null });
        return _addIceCandidate(cand);
      };

      return pc;
    }

    WrappedPC.prototype = NativePC.prototype;
    Object.setPrototypeOf(WrappedPC, NativePC);
    window.RTCPeerConnection = WrappedPC;
  }

  function respond(requestId, ok, result, error) {
    window.postMessage({
      source: "wyze-ext",
      type: "WYZE_EXT_EVENT",
      requestId,
      ok,
      result,
      error
    }, "*");
  }

  function respondProgress(requestId, progress) {
    window.postMessage({
      source: "wyze-ext",
      type: "WYZE_EXT_PROGRESS",
      requestId,
      ok: true,
      progress
    }, "*");
  }

  window.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.source !== "wyze-ext" || data.type !== "WYZE_EXT_CMD") return;
    const { cmd, payload, requestId } = data;
    (async () => {
      if (cmd === "recordSequential") {
        const names = payload.names || [];
        const durationMs = Number(payload.durationMs || 10000);
        const tag = payload.tag || `${durationMs}ms`;
        const minBytes = Number(payload.minBytes || 0);
        const maxRetries = Number(payload.maxRetries || 0);
        window.__wyzeRecordProgressCb = (progress) => respondProgress(requestId, progress);
        const result = await recordSequential({ names, durationMs, tag, minBytes, maxRetries });
        window.__wyzeRecordProgressCb = null;
        respond(requestId, true, result, null);
        return;
      }
      if (cmd === "recordLoop") {
        const names = payload.names || [];
        const durationMs = Number(payload.durationMs || 10000);
        const totalMs = Number(payload.totalMs || 0);
        const tag = payload.tag || `${durationMs}ms`;
        const minBytes = Number(payload.minBytes || 0);
        const maxRetries = Number(payload.maxRetries || 0);
        if (!totalMs || totalMs <= 0) throw new Error("totalMs must be > 0");
        window.__wyzeRecordProgressCb = (progress) => respondProgress(requestId, progress);
        const result = await recordLoop({ names, durationMs, totalMs, tag, minBytes, maxRetries });
        window.__wyzeRecordProgressCb = null;
        respond(requestId, true, result, null);
        return;
      }
      if (cmd === "recordOne") {
        const name = payload.name;
        const durationMs = Number(payload.durationMs || 10000);
        const tag = payload.tag || `${durationMs}ms`;
        const minBytes = Number(payload.minBytes || 0);
        const maxRetries = Number(payload.maxRetries || 0);
        const result = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
        respond(requestId, true, result, null);
        return;
      }
      if (cmd === "setUpload") {
        state.uploads.enabled = !!payload.enabled;
        state.uploads.url = String(payload.url || "");
        state.uploads.mode = payload.mode || "download";
        respond(requestId, true, { ok: true }, null);
        return;
      }
      if (cmd === "pickDir") {
        const res = await pickDir();
        respond(requestId, true, res, null);
        return;
      }
      if (cmd === "clearDir") {
        const res = await clearDir();
        respond(requestId, true, res, null);
        return;
      }
      if (cmd === "dirStatus") {
        const res = await dirStatus();
        respond(requestId, true, res, null);
        return;
      }
      if (cmd === "dumpStats") {
        const out = [];
        for (let i = 0; i < state.pcs.length; i++) {
          const pc = state.pcs[i];
          const stats = await pc.getStats();
          const rows = [];
          stats.forEach((v) => rows.push(v));
          out.push({ pcId: i, stats: rows });
        }
        respond(requestId, true, out, null);
        return;
      }
      if (cmd === "stopAll") {
        stopAll();
        respond(requestId, true, { ok: true }, null);
        return;
      }
      respond(requestId, false, null, `Unknown cmd: ${cmd}`);
    })().catch((err) => {
      respond(requestId, false, null, String(err && err.message ? err.message : err));
    });
  });

  installHooks();
})();
