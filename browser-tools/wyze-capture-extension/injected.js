(() => {
  "use strict";

  if (window.__wyzeRTCInjected) return;
  window.__wyzeRTCInjected = true;

  const state = {
    pcs: [],
    audioTracks: [],
    logs: [],
    events: [],
    eventSeq: 0,
    sessionId: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    uploads: {
      enabled: false,
      url: "",
      mode: "download"
    }
  };
  const MAX_EVENTS = 5000;

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

  function emitEvent(type, payload = {}) {
    const row = {
      seq: state.eventSeq++,
      ts: new Date().toISOString(),
      sessionId: state.sessionId,
      type: String(type || "unknown"),
      pageUrl: location.href,
      payload
    };
    state.events.push(row);
    if (state.events.length > MAX_EVENTS) {
      state.events.splice(0, state.events.length - MAX_EVENTS);
    }
    return row;
  }

  function elementText(el) {
    if (!el || typeof el.textContent !== "string") return "";
    return el.textContent.replace(/\s+/g, " ").trim().slice(0, 500);
  }

  function elementSelector(el) {
    if (!el || !el.nodeType || el.nodeType !== 1) return "";
    const parts = [];
    let cur = el;
    for (let i = 0; i < 6 && cur && cur.nodeType === 1; i += 1) {
      let part = String(cur.tagName || "").toLowerCase();
      if (!part) break;
      if (cur.id) {
        part += `#${String(cur.id).replace(/[^a-zA-Z0-9_-]/g, "")}`;
        parts.unshift(part);
        break;
      }
      if (cur.classList && cur.classList.length) {
        const cls = Array.from(cur.classList).slice(0, 2).join(".");
        if (cls) part += `.${cls.replace(/[^a-zA-Z0-9_.-]/g, "")}`;
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(" > ").slice(0, 500);
  }

  function targetMeta(target) {
    const el = target && target.nodeType === 1
      ? target
      : target && target.parentElement ? target.parentElement : null;
    if (!el) return {};
    const role = el.getAttribute ? (el.getAttribute("role") || "") : "";
    const aria = el.getAttribute ? (el.getAttribute("aria-label") || "") : "";
    const title = el.getAttribute ? (el.getAttribute("title") || "") : "";
    const className = typeof el.className === "string" ? el.className.slice(0, 300) : "";
    const id = el.id ? String(el.id).slice(0, 120) : "";
    return {
      tag: String(el.tagName || "").toLowerCase(),
      id,
      className,
      role: String(role || "").slice(0, 200),
      ariaLabel: String(aria || "").slice(0, 300),
      title: String(title || "").slice(0, 300),
      text: elementText(el),
      selector: elementSelector(el)
    };
  }

  function reconnectSignal(meta) {
    const hay = [
      meta && meta.text ? meta.text : "",
      meta && meta.ariaLabel ? meta.ariaLabel : "",
      meta && meta.title ? meta.title : "",
      meta && meta.id ? meta.id : "",
      meta && meta.className ? meta.className : ""
    ].join(" ").toLowerCase();
    return /(reconnect|retry|try again|re-?connect|refresh|resume|reload|restore)/i.test(hay);
  }

  function findCameraNameFromNode(node) {
    let cur = node && node.nodeType === 1 ? node : node && node.parentElement ? node.parentElement : null;
    for (let i = 0; i < 8 && cur; i += 1) {
      if (cur.matches && cur.matches("li.MuiImageListItem-root")) {
        const title = cur.querySelector("p.MuiTypography-root.MuiTypography-body2");
        if (title && title.textContent) return title.textContent.trim();
      }
      cur = cur.parentElement;
    }
    return "";
  }

  function isInsideOverlay(node) {
    let cur = node && node.nodeType === 1 ? node : node && node.parentElement ? node.parentElement : null;
    for (let i = 0; i < 10 && cur; i += 1) {
      if (cur.id === "wyze-overlay-root") return true;
      cur = cur.parentElement;
    }
    return false;
  }

  window.__wyzeEventLog = {
    sessionId: state.sessionId,
    dump(limit = 500, type = "") {
      const n = Math.max(1, Math.min(MAX_EVENTS, Number(limit || 500)));
      let rows = state.events;
      if (type) rows = rows.filter((r) => r && r.type === String(type));
      return rows.slice(-n);
    },
    clear() {
      state.events = [];
      return { ok: true };
    }
  };

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
    const exists = state.audioTracks.some((x) => x.trackId === track.id);
    if (exists) return;
    state.audioTracks.push({
      track,
      trackId: track.id,
      label: track.label || "",
      kind: track.kind || "",
      enabled: !!track.enabled,
      muted: !!track.muted,
      readyState: track.readyState || "",
      ...meta,
      firstSeen: new Date().toISOString()
    });
    try {
      if (!track.__wyzeListenersInstalled) {
        track.__wyzeListenersInstalled = true;
        track.addEventListener("mute", () => {
          emitEvent("audio_track_mute", { trackId: track.id, label: track.label || "", pcId: meta && meta.pcId != null ? meta.pcId : null });
        });
        track.addEventListener("unmute", () => {
          emitEvent("audio_track_unmute", { trackId: track.id, label: track.label || "", pcId: meta && meta.pcId != null ? meta.pcId : null });
        });
        track.addEventListener("ended", () => {
          emitEvent("audio_track_ended", { trackId: track.id, label: track.label || "", pcId: meta && meta.pcId != null ? meta.pcId : null });
        });
      }
    } catch (_) {}
    window.__wyzeLastRemoteAudioTrack = track;
    emitEvent("audio_track_seen", {
      trackId: track.id,
      label: track.label || "",
      muted: !!track.muted,
      enabled: !!track.enabled,
      readyState: track.readyState || "",
      pcId: meta && meta.pcId != null ? meta.pcId : null,
      source: meta && meta.source ? meta.source : "",
      streamIds: Array.isArray(meta && meta.streamIds) ? meta.streamIds : []
    });
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

  function getStreamContextForCamera(name) {
    const container = findCameraElementByName(name);
    if (!container) throw new Error(`Camera not found: ${name}`);
    const video = getVideoFromContainer(container);
    if (!video) throw new Error(`No video element for camera: ${name}`);
    if (typeof video.captureStream !== "function") {
      throw new Error("captureStream() not available on video element");
    }
    const stream = video.captureStream();
    if (!stream) throw new Error(`captureStream() returned null for: ${name}`);
    return { container, video, stream };
  }

  function summarizeTrack(track) {
    if (!track) return null;
    let settings = {};
    let constraints = {};
    try { settings = track.getSettings ? track.getSettings() : {}; } catch (_) {}
    try { constraints = track.getConstraints ? track.getConstraints() : {}; } catch (_) {}
    return {
      id: track.id || "",
      kind: track.kind || "",
      label: track.label || "",
      enabled: !!track.enabled,
      muted: !!track.muted,
      readyState: track.readyState || "",
      settings,
      constraints
    };
  }

  function pickInterestingAttributes(el) {
    if (!el || !el.getAttributeNames) return {};
    const out = {};
    const names = el.getAttributeNames();
    for (const key of names) {
      const lower = String(key || "").toLowerCase();
      const val = el.getAttribute(key);
      if (val == null || val === "") continue;
      if (/^data-/.test(lower) || /id|uuid|camera|device|stream|track|mac|serial|channel/.test(lower)) {
        out[key] = String(val).slice(0, 500);
      }
    }
    return out;
  }

  function summarizeDomHints(container, video) {
    const out = {};
    const containerAttrs = pickInterestingAttributes(container);
    if (Object.keys(containerAttrs).length) out.container = containerAttrs;
    const videoAttrs = pickInterestingAttributes(video);
    if (Object.keys(videoAttrs).length) out.video = videoAttrs;
    let parent = container && container.parentElement ? container.parentElement : null;
    for (let i = 0; i < 3 && parent; i += 1) {
      const attrs = pickInterestingAttributes(parent);
      if (Object.keys(attrs).length) {
        out[`parent_${i + 1}`] = attrs;
      }
      parent = parent.parentElement;
    }
    return out;
  }

  function pcMatchesForTrackId(trackId) {
    if (!trackId) return [];
    const rows = [];
    for (const row of state.audioTracks) {
      if (row.trackId !== trackId) continue;
      rows.push({
        pcId: row.pcId,
        source: row.source || "",
        firstSeen: row.firstSeen || "",
        streamIds: Array.isArray(row.streamIds) ? row.streamIds : []
      });
    }
    return rows;
  }

  function buildStreamSnapshot({ name, container, video, stream }) {
    const srcObject = video && video.srcObject ? video.srcObject : null;
    const capturedTracks = stream ? stream.getTracks().map((t) => summarizeTrack(t)) : [];
    const audioTracks = stream ? stream.getAudioTracks().map((t) => summarizeTrack(t)) : [];
    const videoTracks = stream ? stream.getVideoTracks().map((t) => summarizeTrack(t)) : [];
    const matchRows = [];
    for (const t of audioTracks) {
      const matches = pcMatchesForTrackId(t && t.id ? t.id : "");
      for (const m of matches) matchRows.push({ trackId: t.id, ...m });
    }
    return {
      cameraName: name,
      cameraKey: safeName(name),
      pageUrl: location.href,
      capturedAt: new Date().toISOString(),
      media: {
        currentSrc: video && video.currentSrc ? video.currentSrc : "",
        src: video && video.src ? video.src : "",
        readyState: video ? Number(video.readyState || 0) : 0,
        videoWidth: video ? Number(video.videoWidth || 0) : 0,
        videoHeight: video ? Number(video.videoHeight || 0) : 0,
        paused: !!(video && video.paused),
        muted: !!(video && video.muted),
        srcObject: srcObject ? {
          id: srcObject.id || "",
          active: !!srcObject.active,
          tracks: srcObject.getTracks ? srcObject.getTracks().map((t) => summarizeTrack(t)) : []
        } : null
      },
      capturedStream: {
        id: stream && stream.id ? stream.id : "",
        active: !!(stream && stream.active),
        tracks: capturedTracks,
        audioTracks,
        videoTracks
      },
      webrtc: {
        pcCount: state.pcs.length,
        matchedAudioTracks: matchRows,
        pcStates: state.pcs.map((pc, pcId) => ({
          pcId,
          connectionState: String(pc && pc.connectionState ? pc.connectionState : ""),
          iceConnectionState: String(pc && pc.iceConnectionState ? pc.iceConnectionState : "")
        }))
      },
      domHints: summarizeDomHints(container, video)
    };
  }

  function getStreamForCamera(name) {
    const ctx = getStreamContextForCamera(name);
    return ctx.stream;
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

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function recordStream({ name, durationMs, tag, minBytes, maxRetries }) {
    const attemptOnce = () => new Promise((resolve, reject) => {
      const ctx = getStreamContextForCamera(name);
      const audioTracks = ctx.stream.getAudioTracks();
      if (!audioTracks || !audioTracks.length) {
        reject(new Error(`No audio tracks for camera: ${name}`));
        return;
      }
      const stream = new MediaStream(audioTracks);
      const mime = chooseAudioMime();
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks = [];
      const startedAt = Date.now();
      const ext = /ogg/.test(rec.mimeType) ? "ogg" : "webm";
      const normalized = safeName(name);
      const filename = `${normalized}__${formatTs(startedAt)}__${tag || `${durationMs}ms`}.${ext}`;
      emitEvent("recording_started", {
        cameraName: name,
        durationMs,
        mimeType: rec.mimeType || mime || "",
        filename,
        startedAt
      });

      rec.ondataavailable = (e) => {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      rec.onerror = (e) => {
        emitEvent("recording_error", {
          cameraName: name,
          message: String((e && e.error && e.error.message) || (e && e.message) || "MediaRecorder error")
        });
        reject(e.error || new Error("MediaRecorder error"));
      };
      rec.onstop = async () => {
        const blob = new Blob(chunks, { type: rec.mimeType || "application/octet-stream" });
        if (minBytes && blob.size < minBytes) {
          emitEvent("recording_too_small", { cameraName: name, bytes: blob.size, minBytes, startedAt });
          log("recording too small", { name, bytes: blob.size, minBytes });
          resolve({ tooSmall: true, bytes: blob.size, startedAt });
          return;
        }
        try {
          await saveOrUpload({ blob, filename, name, startedAt, durationMs });
          emitEvent("recording_saved", { cameraName: name, bytes: blob.size, mimeType: blob.type || "", filename, startedAt });
          resolve({ name, bytes: blob.size, type: blob.type, filename, startedAt });
        } catch (err) {
          emitEvent("recording_save_error", {
            cameraName: name,
            filename,
            message: String(err && err.message ? err.message : err)
          });
          reject(err);
        }
      };

      rec.start(1000);
      log("recording started (audio)", { name, durationMs, mime: rec.mimeType || mime || "" });
      if (durationMs > 0) setTimeout(() => { try { rec.stop(); } catch (_) {} }, durationMs);
    });

    const retries = Number(maxRetries || 0);
    let lastErr = null;
    for (let i = 0; i <= retries; i++) {
      try {
        const res = await attemptOnce();
        if (!res.tooSmall) return res;
        lastErr = new Error(`Recording too small (${res.bytes} bytes, min ${minBytes})`);
      } catch (err) {
        lastErr = err;
      }
      if (i < retries) {
        emitEvent("recording_retry", {
          cameraName: name,
          attempt: i + 1,
          maxRetries: retries,
          reason: String(lastErr && lastErr.message ? lastErr.message : lastErr)
        });
        log("retrying", {
          name,
          attempt: i + 1,
          maxRetries: retries,
          reason: String(lastErr && lastErr.message ? lastErr.message : lastErr)
        });
        await sleep(1000);
      }
    }
    const reason = String(lastErr && lastErr.message ? lastErr.message : "unknown");
    emitEvent("recording_failed", { cameraName: name, attempts: retries + 1, reason });
    throw new Error(`Recording failed after ${retries + 1} attempt(s): ${name} (${reason})`);
  }

  async function saveOrUpload({ blob, filename, name, startedAt, durationMs }) {
    if (state.uploads.mode === "page") {
      await saveToDir({ blob, filename, name, startedAt });
      emitEvent("save_to_folder", { cameraName: name, filename, bytes: blob.size });
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
        emitEvent("upload_failed", { cameraName: name, filename, status: res.status, url: state.uploads.url });
        throw new Error(`Upload failed ${res.status}`);
      }
      emitEvent("upload_ok", { cameraName: name, filename, status: res.status, url: state.uploads.url });
      log("uploaded", { name, filename, status: res.status });
      return;
    }

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    emitEvent("download_saved", { cameraName: name, filename, bytes: blob.size, mimeType: blob.type || "" });
    log("saved", { name, filename, bytes: blob.size, type: blob.type });
  }

  async function recordSequential({ names, durationMs, tag, minBytes, maxRetries }) {
    const out = [];
    const startedAt = Date.now();
    let failed = 0;
    for (const name of names) {
      let res = null;
      let err = null;
      try {
        res = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
        out.push(res);
      } catch (e) {
        failed += 1;
        err = e;
        log("recording failed, moving to next camera", {
          name,
          error: String(e && e.message ? e.message : e)
        });
      }
      if (window.__wyzeRecordProgressCb) {
        let totalBytes = 0;
        for (const r of out) totalBytes += Number(r && r.bytes ? r.bytes : 0);
        window.__wyzeRecordProgressCb({
          mode: "sequential",
          completed: out.length + failed,
          successful: out.length,
          failed,
          totalPlanned: names.length,
          currentName: name,
          lastBytes: Number(res && res.bytes ? res.bytes : 0),
          lastError: err ? String(err && err.message ? err.message : err) : "",
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
    let failed = 0;
    while (Date.now() - start < totalMs) {
      const name = names[idx % names.length];
      idx += 1;
      let res = null;
      let err = null;
      try {
        res = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
        out.push(res);
      } catch (e) {
        failed += 1;
        err = e;
        log("loop recording failed, moving to next camera", {
          name,
          error: String(e && e.message ? e.message : e)
        });
      }
      if (window.__wyzeRecordProgressCb) {
        let totalBytes = 0;
        for (const r of out) totalBytes += Number(r && r.bytes ? r.bytes : 0);
        window.__wyzeRecordProgressCb({
          mode: "loop",
          completed: out.length + failed,
          successful: out.length,
          failed,
          totalPlanned: null,
          currentName: name,
          lastBytes: Number(res && res.bytes ? res.bytes : 0),
          lastError: err ? String(err && err.message ? err.message : err) : "",
          totalBytes,
          elapsedMs: Date.now() - start,
          totalMs
        });
      }
    }
    return out;
  }

  async function recordParallel({ names, durationMs, tag, minBytes, maxRetries, concurrency, totalMs }) {
    const out = [];
    if (!names || !names.length) return out;
    const startedAt = Date.now();
    let failed = 0;
    let nextIdx = 0;
    let totalBytes = 0;
    const workerCount = Math.max(1, Math.min(names.length, Number(concurrency || 1)));
    const timedLoop = Number(totalMs || 0) > 0;
    const maxMs = Math.max(0, Number(totalMs || 0));

    const worker = async (workerId) => {
      while (true) {
        if (timedLoop && (Date.now() - startedAt) >= maxMs) return;
        const idx = nextIdx;
        nextIdx += 1;
        if (!timedLoop && idx >= names.length) return;
        const name = names[idx % names.length];
        let res = null;
        let err = null;
        try {
          res = await recordStream({ name, durationMs, tag, minBytes, maxRetries });
          out.push(res);
          totalBytes += Number(res && res.bytes ? res.bytes : 0);
        } catch (e) {
          failed += 1;
          err = e;
          log("parallel recording failed, moving to next camera", {
            workerId,
            name,
            error: String(e && e.message ? e.message : e)
          });
        }
        if (window.__wyzeRecordProgressCb) {
          window.__wyzeRecordProgressCb({
            mode: timedLoop ? "parallel-loop" : "parallel",
            completed: out.length + failed,
            successful: out.length,
            failed,
            totalPlanned: timedLoop ? null : names.length,
            currentName: name,
            lastBytes: Number(res && res.bytes ? res.bytes : 0),
            lastError: err ? String(err && err.message ? err.message : err) : "",
            totalBytes,
            elapsedMs: Date.now() - startedAt,
            totalMs: timedLoop ? maxMs : null
          });
        }
      }
    };

    const workers = [];
    for (let i = 0; i < workerCount; i += 1) workers.push(worker(i));
    await Promise.all(workers);
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
    emitEvent("injected_loaded", { href: location.href });
    log("injected loaded", location.href);

    document.addEventListener("click", (e) => {
      try {
        const target = e && e.target ? e.target : null;
        if (!target || isInsideOverlay(target)) return;
        const meta = targetMeta(target);
        const cameraName = findCameraNameFromNode(target);
        const payload = {
          ...meta,
          cameraName: cameraName || "",
          x: Number(e.clientX || 0),
          y: Number(e.clientY || 0)
        };
        emitEvent("ui_click", payload);
        if (reconnectSignal(meta)) {
          emitEvent("reconnect_click_signal", payload);
          log("reconnect click signal", payload);
        }
      } catch (_) {}
    }, true);

    const origFetch = window.fetch;
    window.fetch = async function (...args) {
      const res = await origFetch.apply(this, args);
      try {
        const url = String(args[0]?.url || args[0] || "");
        const ct = res.headers?.get?.("content-type") || "";
        if (/get-streams|webrtc|kinesis|signal|ice|turn/i.test(url)) {
          const txt = await res.clone().text();
          emitEvent("network_fetch_webrtc", { url, status: res.status, contentType: ct, bodyPreview: txt.slice(0, 2000) });
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
            emitEvent("network_xhr_webrtc", { ...this.__wyzeMeta, status: this.status, bodyPreview: txt.slice(0, 2000) });
            log("xhr", { ...this.__wyzeMeta, status: this.status, bodyPreview: txt.slice(0, 2000) });
          }
        } catch (_) {}
      });
      return xs.call(this, body);
    };

    const NativePC = window.RTCPeerConnection;
    if (!NativePC) {
      emitEvent("webrtc_missing", { message: "RTCPeerConnection missing in top frame" });
      log("RTCPeerConnection missing in top frame");
      return;
    }

    function WrappedPC(...args) {
      const pc = new NativePC(...args);
      const pcId = state.pcs.push(pc) - 1;
      pc.__wyzePcId = pcId;
      emitEvent("pc_created", { pcId, config: args[0] || null });
      log("pc created", { pcId, config: args[0] });

      pc.addEventListener("track", (e) => {
        emitEvent("pc_track", {
          pcId,
          kind: e.track?.kind || "",
          trackId: e.track?.id || "",
          label: e.track?.label || "",
          streams: (e.streams || []).map((s) => s.id)
        });
        log("pc track", {
          pcId,
          kind: e.track?.kind,
          id: e.track?.id,
          label: e.track?.label,
          streams: (e.streams || []).map((s) => s.id)
        });
        rememberAudioTrack(e.track, { pcId, source: "track-event", streamIds: (e.streams || []).map((s) => s.id) });
      });

      pc.addEventListener("icecandidate", (e) => {
        emitEvent("ice_candidate", { pcId, candidate: e.candidate?.candidate || null });
        log("icecandidate", { pcId, candidate: e.candidate?.candidate || null });
      });
      pc.addEventListener("iceconnectionstatechange", () => {
        emitEvent("ice_state", { pcId, state: pc.iceConnectionState });
        log("ice state", { pcId, state: pc.iceConnectionState });
      });
      pc.addEventListener("connectionstatechange", () => {
        emitEvent("pc_state", { pcId, state: pc.connectionState });
        log("pc state", { pcId, state: pc.connectionState });
      });

      const _setRemoteDescription = pc.setRemoteDescription.bind(pc);
      pc.setRemoteDescription = async function (desc) {
        emitEvent("set_remote_description", { pcId, type: desc?.type || "", sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        log("setRemoteDescription", { pcId, type: desc?.type, sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        const out = await _setRemoteDescription(desc);
        setTimeout(() => scanReceivers(pc, pcId, "post-remote-desc-500ms"), 500);
        setTimeout(() => scanReceivers(pc, pcId, "post-remote-desc-2000ms"), 2000);
        return out;
      };

      const _setLocalDescription = pc.setLocalDescription.bind(pc);
      pc.setLocalDescription = async function (desc) {
        emitEvent("set_local_description", { pcId, type: desc?.type || "", sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        log("setLocalDescription", { pcId, type: desc?.type, sdpPreview: String(desc?.sdp || "").slice(0, 1000) });
        return _setLocalDescription(desc);
      };

      const _addIceCandidate = pc.addIceCandidate.bind(pc);
      pc.addIceCandidate = async function (cand) {
        emitEvent("add_ice_candidate", { pcId, candidate: cand?.candidate || null });
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
      if (cmd === "recordParallel") {
        const names = payload.names || [];
        const durationMs = Number(payload.durationMs || 10000);
        const tag = payload.tag || `${durationMs}ms`;
        const minBytes = Number(payload.minBytes || 0);
        const maxRetries = Number(payload.maxRetries || 0);
        const concurrency = Number(payload.concurrency || 1);
        window.__wyzeRecordProgressCb = (progress) => respondProgress(requestId, progress);
        const result = await recordParallel({ names, durationMs, tag, minBytes, maxRetries, concurrency, totalMs: 0 });
        window.__wyzeRecordProgressCb = null;
        respond(requestId, true, result, null);
        return;
      }
      if (cmd === "recordParallelLoop") {
        const names = payload.names || [];
        const durationMs = Number(payload.durationMs || 10000);
        const totalMs = Number(payload.totalMs || 0);
        const tag = payload.tag || `${durationMs}ms`;
        const minBytes = Number(payload.minBytes || 0);
        const maxRetries = Number(payload.maxRetries || 0);
        const concurrency = Number(payload.concurrency || 1);
        if (!totalMs || totalMs <= 0) throw new Error("totalMs must be > 0");
        window.__wyzeRecordProgressCb = (progress) => respondProgress(requestId, progress);
        const result = await recordParallel({ names, durationMs, tag, minBytes, maxRetries, concurrency, totalMs });
        window.__wyzeRecordProgressCb = null;
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
      if (cmd === "dumpStreamInfo") {
        const names = Array.isArray(payload.names) ? payload.names.filter(Boolean) : [];
        const targets = names.length
          ? names
          : Array.from(document.querySelectorAll("li.MuiImageListItem-root p.MuiTypography-root.MuiTypography-body2"))
            .map((el) => (el && el.textContent ? el.textContent.trim() : ""))
            .filter(Boolean);
        const uniqueTargets = Array.from(new Set(targets));
        const out = [];
        for (const name of uniqueTargets) {
          try {
            const ctx = getStreamContextForCamera(name);
            out.push({ ok: true, name, snapshot: buildStreamSnapshot({ name, container: ctx.container, video: ctx.video, stream: ctx.stream }) });
          } catch (err) {
            out.push({ ok: false, name, error: String(err && err.message ? err.message : err) });
          }
        }
        respond(requestId, true, out, null);
        return;
      }
      if (cmd === "dumpEventLog") {
        const limit = Math.max(1, Math.min(MAX_EVENTS, Number(payload.limit || 500)));
        const type = payload.type ? String(payload.type) : "";
        let rows = state.events;
        if (type) rows = rows.filter((r) => r && r.type === type);
        respond(requestId, true, rows.slice(-limit), null);
        return;
      }
      if (cmd === "clearEventLog") {
        state.events = [];
        respond(requestId, true, { ok: true }, null);
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
