(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const status = $("status");

  async function load() {
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

  async function save() {
    const cfg = {
      durationMs: Number($("duration").value || 10000),
      runHours: Number($("runHours").value || 0),
      tag: $("tag").value || "",
      minBytes: Number($("minBytes").value || 0),
      maxRetries: Number($("maxRetries").value || 0),
      uploadEnabled: $("uploadEnabled").checked && !$("useRecorder").checked,
      uploadUrl: $("uploadUrl").value || "",
      useRecorder: $("useRecorder").checked
    };
    await chrome.storage.local.set({ wyzeDefaults: cfg });
    status.textContent = "Saved";
    setTimeout(() => (status.textContent = ""), 1500);
  }

  $("save").addEventListener("click", () => save().catch(() => {}));
  load().catch(() => {});
})();
