(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const dirStatus = $("dirStatus");
  const lastSaved = $("lastSaved");
  let dirHandle = null;

  const DB_NAME = "wyze-recorder";
  const STORE = "handles";

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
    dirStatus.textContent = "Folder selected";
  }

  async function clearDir() {
    dirHandle = null;
    await clearHandle();
    dirStatus.textContent = "Folder cleared";
  }

  async function init() {
    try {
      dirHandle = await loadHandle();
      if (dirHandle) {
        const ok = await ensurePermission(dirHandle);
        dirStatus.textContent = ok ? "Folder ready" : "Folder needs permission";
      } else {
        dirStatus.textContent = "No folder selected";
      }
    } catch (err) {
      dirStatus.textContent = "Folder init failed";
    }
  }

  async function saveBlob(msg) {
    if (!dirHandle) throw new Error("No folder selected");
    const ok = await ensurePermission(dirHandle);
    if (!ok) throw new Error("Permission denied");
    if (!msg || !msg.buffer) throw new Error("Missing blob buffer");
    const fileHandle = await dirHandle.getFileHandle(msg.filename, { create: true });
    const writable = await fileHandle.createWritable();
    const blob = new Blob([msg.buffer], { type: msg.mimeType || "application/octet-stream" });
    await writable.write(blob);
    await writable.close();
    lastSaved.textContent = `Saved ${msg.filename} (${blob.size} bytes)`;
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "WYZE_SAVE_BLOB") return;
    saveBlob(msg.payload).catch((err) => {
      lastSaved.textContent = `Save failed: ${String(err && err.message ? err.message : err)}`;
    });
  });

  $("pickDir").addEventListener("click", () => pickDir().catch((e) => (dirStatus.textContent = String(e.message || e))));
  $("clearDir").addEventListener("click", () => clearDir().catch((e) => (dirStatus.textContent = String(e.message || e))));
  init();
})();
