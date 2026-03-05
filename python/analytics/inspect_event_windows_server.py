#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import wave
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

import matplotlib
import pandas as pd
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_SAMPLES = (
    "/mnt/d/datasets/svwatergo/derived/"
    "dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet"
)

UI_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Event Window Inspector</title>
  <style>
    body { font-family: sans-serif; margin: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
    label { font-size: 12px; color: #333; display:block; }
    input, select, button { padding: 6px; font-size: 13px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #ddd; padding: 6px; font-size: 12px; text-align: left; }
    th { background: #f3f3f3; position: sticky; top: 0; }
    .panel { border: 1px solid #ddd; padding: 10px; margin-top: 12px; }
    pre { white-space: pre-wrap; font-size: 12px; max-height: 280px; overflow: auto; }
    .mono { font-family: monospace; }
  </style>
</head>
<body>
  <h2>Event Window Inspector</h2>
  <div id="summary" class="mono"></div>
  <div style="margin:6px 0;">
    <a href="#" onclick="loadDir(''); return false;">Browse Raw Dataset</a>
    |
    <a href="/raw/" target="_blank" rel="noopener">Open Static /raw/ Browser</a>
  </div>

  <div class="panel">
    <div class="row">
      <div><label>split</label><input id="split" value="" /></div>
      <div><label>class</label><input id="klass" value="" /></div>
      <div><label>source</label><input id="source" value="" /></div>
      <div><label>day</label><input id="day" value="" /></div>
      <div><label>min segments</label><input id="minSeg" type="number" value="1" /></div>
      <div><label>limit</label><input id="limit" type="number" value="200" /></div>
      <div><label>&nbsp;</label><button onclick="loadWindows()">Load Windows</button></div>
    </div>
    <table id="windowsTbl">
      <thead><tr>
        <th>event_window_id</th><th>split</th><th>class</th><th>segments</th><th>seconds</th><th>source</th><th>day</th><th>start</th><th>end</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <div><b>Selected Window</b>: <span id="selectedWindow" class="mono"></span></div>
    <table id="segmentsTbl">
      <thead><tr>
        <th>sample_id</th><th>start</th><th>end</th><th>class</th><th>states</th><th>audio</th><th>spec</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <div><b>Segment Media</b>: <span id="mediaInfo" class="mono"></span></div>
    <audio id="audioPlayer" controls style="width:100%; margin-top:8px;"></audio>
    <div style="margin-top:8px;">
      <img id="specImg" style="max-width:100%; border:1px solid #ddd;" />
    </div>
  </div>

  <div class="panel">
    <div class="row">
      <div style="min-width: 60%">
        <label>raw file path (absolute, under allowed roots)</label>
        <input id="filePath" style="width:100%" />
      </div>
      <div><label>rows</label><input id="fileRows" type="number" value="20" /></div>
      <div><label>&nbsp;</label><button onclick="loadFile()">View File</button></div>
    </div>
    <pre id="filePreview"></pre>
  </div>

  <div class="panel">
    <div><b>Directory Browser</b>: <span id="dirPath" class="mono"></span></div>
    <table id="dirTbl">
      <thead><tr><th>name</th><th>type</th><th>size</th><th>path</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

<script>
async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}
async function loadSummary() {
  const d = await jget('/api/summary');
  document.getElementById('summary').textContent =
    `rows=${d.n_rows} windows=${d.n_windows} splits=${JSON.stringify(d.by_split)}`;
  window.__defaultBrowseRoot = d.samples_parquet.split('/').slice(0, -4).join('/');
}
function esc(x) { return String(x ?? ''); }
async function loadWindows() {
  const q = new URLSearchParams();
  const split = document.getElementById('split').value.trim();
  const klass = document.getElementById('klass').value.trim();
  const source = document.getElementById('source').value.trim();
  const day = document.getElementById('day').value.trim();
  const minSeg = document.getElementById('minSeg').value.trim();
  const limit = document.getElementById('limit').value.trim();
  if (split) q.set('split', split);
  if (klass) q.set('primary_class', klass);
  if (source) q.set('audio_source', source);
  if (day) q.set('day_utc', day);
  if (minSeg) q.set('min_segments', minSeg);
  if (limit) q.set('limit', limit);
  const d = await jget('/api/windows?' + q.toString());
  const tb = document.querySelector('#windowsTbl tbody');
  tb.innerHTML = '';
  for (const w of d.windows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><a href="#" data-id="${esc(w.event_window_id)}">${esc(w.event_window_id)}</a></td>
      <td>${esc(w.split)}</td><td>${esc(w.primary_class)}</td><td>${esc(w.n_segments)}</td>
      <td>${esc(w.window_seconds)}</td><td>${esc(w.audio_source)}</td><td>${esc(w.day_utc)}</td>
      <td>${esc(w.start_ts)}</td><td>${esc(w.end_ts)}</td>`;
    tb.appendChild(tr);
  }
  for (const a of tb.querySelectorAll('a[data-id]')) {
    a.onclick = async (ev) => {
      ev.preventDefault();
      await loadWindow(ev.target.getAttribute('data-id'));
    };
  }
}
async function loadWindow(id) {
  document.getElementById('selectedWindow').textContent = id;
  const d = await jget('/api/window?event_window_id=' + encodeURIComponent(id));
  const tb = document.querySelector('#segmentsTbl tbody');
  tb.innerHTML = '';
  for (const s of d.segments) {
    const tr = document.createElement('tr');
    const audioPath = esc(s.segment_path || '');
    const melPath = esc(s.mel_shard_path || '');
    const melIdx = esc(s.mel_shard_local_index ?? 0);
    tr.innerHTML = `<td class="mono">${esc(s.sample_id || '')}</td>
      <td>${esc(s.segment_start_ts_utc || '')}</td>
      <td>${esc(s.segment_end_ts_utc || '')}</td>
      <td>${esc(s.primary_class || '')}</td>
      <td>${esc(s.states_seen || '')}</td>
      <td><button data-audio="${audioPath}">Play</button></td>
      <td><button data-audio="${audioPath}" data-mel="${melPath}" data-mel-idx="${melIdx}">Spec</button></td>`;
    tb.appendChild(tr);
  }
  for (const b of tb.querySelectorAll('button[data-audio]')) {
    b.onclick = (ev) => {
      const btn = ev.target;
      const path = btn.getAttribute('data-audio') || '';
      const mel = btn.getAttribute('data-mel') || '';
      const melIdx = btn.getAttribute('data-mel-idx') || '0';
      if (btn.textContent === 'Play') {
        showAudio(path);
      } else {
        showSpec(path, mel, melIdx);
      }
    };
  }
}
function showAudio(path) {
  const p = document.getElementById('audioPlayer');
  p.src = '/audio?path=' + encodeURIComponent(path);
  p.play().catch(() => {});
  document.getElementById('mediaInfo').textContent = `audio: ${path}`;
}
function showSpec(audioPath, melPath, melIdx) {
  const img = document.getElementById('specImg');
  let url = '';
  if (melPath) {
    url = '/spectrogram?mel_shard_path=' + encodeURIComponent(melPath) + '&mel_index=' + encodeURIComponent(melIdx || '0');
  } else {
    url = '/spectrogram?path=' + encodeURIComponent(audioPath);
  }
  img.src = url;
  document.getElementById('mediaInfo').textContent = `spec: ${audioPath}`;
}
async function loadFile() {
  const p = document.getElementById('filePath').value.trim();
  const rows = document.getElementById('fileRows').value.trim();
  if (!p) return;
  const d = await jget('/api/file?path=' + encodeURIComponent(p) + '&rows=' + encodeURIComponent(rows || '20'));
  document.getElementById('filePreview').textContent = JSON.stringify(d, null, 2);
}
async function loadDir(path) {
  const target = path && path.length ? path : (window.__defaultBrowseRoot || '');
  const d = await jget('/api/files?path=' + encodeURIComponent(target));
  document.getElementById('dirPath').textContent = d.path;
  const tb = document.querySelector('#dirTbl tbody');
  tb.innerHTML = '';
  for (const it of d.items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><a href="#" data-p="${esc(it.path)}">${esc(it.name)}</a></td>
      <td>${it.is_dir ? 'dir' : 'file'}</td>
      <td>${esc(it.size ?? '')}</td>
      <td class="mono">${esc(it.path)}</td>`;
    tb.appendChild(tr);
  }
  for (const a of tb.querySelectorAll('a[data-p]')) {
    a.onclick = async (ev) => {
      ev.preventDefault();
      const p = ev.target.getAttribute('data-p') || '';
      const row = ev.target.closest('tr');
      const isDir = row && row.children[1] && row.children[1].textContent === 'dir';
      if (isDir) {
        await loadDir(p);
      } else {
        document.getElementById('filePath').value = p;
        await loadFile();
      }
    };
  }
}
loadSummary().catch(e => alert(e.message));
loadWindows().catch(e => alert(e.message));
loadDir('').catch(e => console.log(e.message));
</script>
</body>
</html>
"""


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Basic web inspector for event windows and raw dataset files.")
    p.add_argument("--samples-parquet", default=DEFAULT_SAMPLES)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Allowed root for /api/file and /api/files (repeatable). Defaults to parent of samples parquet.",
    )
    return p


def _default_allowed_roots(samples: Path) -> List[Path]:
    for parent in samples.parents:
        if parent.name == "derived":
            return [parent]
    return [samples.parent]


class AppState:
    def __init__(self, samples_path: Path, allowed_roots: List[Path]) -> None:
        self.samples_path = samples_path
        self.allowed_roots = allowed_roots
        self.df = pd.read_parquet(samples_path)
        required = [
            "event_window_id",
            "split",
            "primary_class",
            "audio_source",
            "day_utc",
            "segment_start_ts_utc",
            "segment_end_ts_utc",
        ]
        missing = [c for c in required if c not in self.df.columns]
        if missing:
            raise ValueError(f"samples parquet missing required columns: {', '.join(missing)}")

        self.df["segment_start_ts_utc"] = pd.to_datetime(self.df["segment_start_ts_utc"], utc=True, errors="coerce")
        self.df["segment_end_ts_utc"] = pd.to_datetime(self.df["segment_end_ts_utc"], utc=True, errors="coerce")
        self.df["window_seconds"] = (
            self.df["segment_end_ts_utc"] - self.df["segment_start_ts_utc"]
        ).dt.total_seconds()
        self._windows_df = self._build_windows(self.df)

    @staticmethod
    def _build_windows(df: pd.DataFrame) -> pd.DataFrame:
        g = (
            df.groupby("event_window_id", dropna=False)
            .agg(
                split=("split", "first"),
                primary_class=("primary_class", "first"),
                audio_source=("audio_source", "first"),
                day_utc=("day_utc", "first"),
                n_segments=("event_window_id", "size"),
                start_ts=("segment_start_ts_utc", "min"),
                end_ts=("segment_end_ts_utc", "max"),
                total_segment_seconds=("window_seconds", "sum"),
            )
            .reset_index()
        )
        g["window_seconds"] = (g["end_ts"] - g["start_ts"]).dt.total_seconds()
        g["start_ts"] = g["start_ts"].astype("string")
        g["end_ts"] = g["end_ts"].astype("string")
        return g.sort_values(["n_segments", "window_seconds"], ascending=[False, False]).reset_index(drop=True)

    def summary(self) -> Dict[str, Any]:
        by_split = self.df["split"].astype("string").value_counts(dropna=False).to_dict()
        by_class = self.df["primary_class"].astype("string").value_counts(dropna=False).to_dict()
        return {
            "samples_parquet": str(self.samples_path),
            "n_rows": int(len(self.df)),
            "n_windows": int(self.df["event_window_id"].nunique(dropna=True)),
            "by_split": {str(k): int(v) for k, v in by_split.items()},
            "by_class": {str(k): int(v) for k, v in by_class.items()},
        }

    def windows(
        self,
        *,
        split: str = "",
        primary_class: str = "",
        audio_source: str = "",
        day_utc: str = "",
        min_segments: int = 1,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        out = self._windows_df
        if split:
            out = out[out["split"].astype("string") == split]
        if primary_class:
            out = out[out["primary_class"].astype("string") == primary_class]
        if audio_source:
            out = out[out["audio_source"].astype("string") == audio_source]
        if day_utc:
            out = out[out["day_utc"].astype("string") == day_utc]
        out = out[out["n_segments"] >= int(min_segments)]
        total = int(len(out))
        if offset > 0:
            out = out.iloc[offset:]
        out = out.head(max(1, min(int(limit), 5000)))
        return {"total": total, "offset": int(offset), "limit": int(limit), "windows": out.to_dict(orient="records")}

    def one_window(self, event_window_id: str, limit: int = 2000) -> Dict[str, Any]:
        out = self.df[self.df["event_window_id"].astype("string") == str(event_window_id)].copy()
        out = out.sort_values("segment_start_ts_utc", ascending=True)
        total = int(len(out))
        keep_cols = [
            "sample_id",
            "split",
            "primary_class",
            "audio_source",
            "day_utc",
            "segment_start_ts_utc",
            "segment_end_ts_utc",
            "segment_path",
            "mel_shard_path",
            "window_seconds",
            "overlap_s_producing",
            "overlap_s_delivering",
            "overlap_s_flushing",
            "overlap_s_quiet",
            "states_seen",
        ]
        cols = [c for c in keep_cols if c in out.columns]
        out = out[cols].head(max(1, min(int(limit), 10000))).copy()
        for c in ["segment_start_ts_utc", "segment_end_ts_utc"]:
            if c in out.columns:
                out[c] = out[c].astype("string")
        return {"event_window_id": event_window_id, "total_segments": total, "segments": out.to_dict(orient="records")}

    def read_audio_bytes(self, path: str) -> bytes:
        p = self._check_allowed(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        return p.read_bytes()

    def render_spectrogram_png(
        self,
        *,
        path: str = "",
        mel_shard_path: str = "",
        mel_index: int = 0,
    ) -> bytes:
        if mel_shard_path:
            mel_p = self._check_allowed(mel_shard_path)
            if not mel_p.exists():
                raise FileNotFoundError(str(mel_p))
            with np.load(mel_p, mmap_mode="r") as data:
                key = "mel" if "mel" in data.files else ("arr_0" if "arr_0" in data.files else data.files[0])
                arr = data[key]
                if arr.ndim == 3:
                    idx = max(0, min(int(mel_index), int(arr.shape[0]) - 1))
                    m = np.asarray(arr[idx], dtype=np.float32)
                elif arr.ndim == 2:
                    m = np.asarray(arr, dtype=np.float32)
                else:
                    raise ValueError(f"unsupported mel array shape: {arr.shape}")
            return _plot_matrix_png(m, title=f"Mel Spectrogram idx={mel_index}")

        wav_p = self._check_allowed(path)
        if not wav_p.exists():
            raise FileNotFoundError(str(wav_p))
        with wave.open(str(wav_p), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if sampwidth != 2:
            raise ValueError(f"unsupported wav sample width: {sampwidth} bytes")
        y = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if n_channels > 1:
            y = y.reshape(-1, n_channels).mean(axis=1)
        if y.size == 0:
            raise ValueError("empty wav")
        return _plot_wav_spec_png(y, sample_rate=rate, title=wav_p.name)

    def _check_allowed(self, path_str: str) -> Path:
        p = Path(path_str).expanduser().resolve()
        for root in self.allowed_roots:
            try:
                p.relative_to(root)
                return p
            except Exception:
                continue
        raise PermissionError(f"path outside allowed roots: {p}")

    def list_dir(self, path: str) -> Dict[str, Any]:
        p = self._check_allowed(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if not p.is_dir():
            raise NotADirectoryError(str(p))
        items: List[Dict[str, Any]] = []
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:2000]:
            items.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": (None if child.is_dir() else child.stat().st_size),
                }
            )
        return {"path": str(p), "items": items}

    def preview_file(self, path: str, rows: int = 20) -> Dict[str, Any]:
        p = self._check_allowed(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if p.is_dir():
            return self.list_dir(str(p))
        ext = p.suffix.lower()
        rows = max(1, min(int(rows), 1000))
        if ext == ".parquet":
            df = pd.read_parquet(p).head(rows)
            return {"path": str(p), "kind": "parquet", "rows": int(len(df)), "preview": df.to_dict(orient="records")}
        if ext == ".csv":
            df = pd.read_csv(p).head(rows)
            return {"path": str(p), "kind": "csv", "rows": int(len(df)), "preview": df.to_dict(orient="records")}
        if ext == ".json":
            return {"path": str(p), "kind": "json", "preview": json.loads(p.read_text(encoding="utf-8"))}
        mime, _enc = mimetypes.guess_type(str(p))
        if mime and mime.startswith("text/"):
            txt = p.read_text(encoding="utf-8", errors="replace")
            return {"path": str(p), "kind": "text", "preview": txt[:20000]}
        return {"path": str(p), "kind": "binary", "size_bytes": p.stat().st_size}


def _q1(params: Dict[str, List[str]], key: str, default: str = "") -> str:
    vals = params.get(key)
    if not vals:
        return default
    return str(vals[0])


def _safe_under_root(root: Path, rel_path: str) -> Path:
    target = (root / rel_path.lstrip("/")).resolve()
    target.relative_to(root)
    return target


def _render_dir_listing_html(*, root: Path, req_rel: str, target: Path) -> str:
    title = f"Index of /raw/{req_rel.lstrip('/')}"
    rows: List[str] = []
    if req_rel.strip("/"):
        parent_rel = str(Path(req_rel).parent)
        if parent_rel == ".":
            parent_rel = ""
        rows.append(
            f"<tr><td><a href=\"/raw/{quote(parent_rel)}\">..</a></td><td>dir</td><td></td></tr>"
        )
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        child_rel = str((Path(req_rel) / child.name).as_posix()).lstrip("./")
        href = f"/raw/{quote(child_rel)}"
        ctype = "dir" if child.is_dir() else "file"
        size = "" if child.is_dir() else str(child.stat().st_size)
        rows.append(f"<tr><td><a href=\"{href}\">{child.name}</a></td><td>{ctype}</td><td>{size}</td></tr>")
    return (
        "<!doctype html><html><head><meta charset='utf-8' />"
        "<title>Raw Browser</title>"
        "<style>body{font-family:sans-serif;margin:12px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ddd;padding:6px;font-size:12px;text-align:left}"
        "th{background:#f3f3f3}</style></head><body>"
        f"<h3>{title}</h3>"
        f"<div>root: {root}</div>"
        "<table><thead><tr><th>name</th><th>type</th><th>size</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )


def _plot_matrix_png(m: np.ndarray, *, title: str) -> bytes:
    fig = plt.figure(figsize=(8, 3))
    ax = fig.add_subplot(1, 1, 1)
    ax.imshow(m, aspect="auto", origin="lower", interpolation="nearest")
    ax.set_title(title)
    ax.set_xlabel("frame")
    ax.set_ylabel("mel bin")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def _plot_wav_spec_png(y: np.ndarray, *, sample_rate: int, title: str) -> bytes:
    fig = plt.figure(figsize=(8, 3))
    ax = fig.add_subplot(1, 1, 1)
    ax.specgram(y, NFFT=512, Fs=float(sample_rate), noverlap=256)
    ax.set_title(f"Spectrogram: {title}")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("freq (Hz)")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, obj: Dict[str, Any], code: int = 200) -> None:
            data = json.dumps(obj, indent=2, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_html(self, html: str, code: int = 200) -> None:
            data = html.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_bytes(self, data: bytes, *, content_type: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                q = parse_qs(parsed.query, keep_blank_values=False)
                if path == "/":
                    self._write_html(UI_HTML)
                    return
                if path.startswith("/raw"):
                    root = state.allowed_roots[0]
                    req_rel = unquote(path[len("/raw") :]).lstrip("/")
                    target = _safe_under_root(root, req_rel)
                    if not target.exists():
                        self._write_json({"error": f"not found: {target}"}, code=404)
                        return
                    if target.is_dir():
                        self._write_html(_render_dir_listing_html(root=root, req_rel=req_rel, target=target))
                        return
                    mime, _enc = mimetypes.guess_type(str(target))
                    self._write_bytes(target.read_bytes(), content_type=(mime or "application/octet-stream"))
                    return
                if path == "/api/summary":
                    self._write_json(state.summary())
                    return
                if path == "/api/windows":
                    out = state.windows(
                        split=_q1(q, "split", ""),
                        primary_class=_q1(q, "primary_class", ""),
                        audio_source=_q1(q, "audio_source", ""),
                        day_utc=_q1(q, "day_utc", ""),
                        min_segments=int(_q1(q, "min_segments", "1")),
                        limit=int(_q1(q, "limit", "200")),
                        offset=int(_q1(q, "offset", "0")),
                    )
                    self._write_json(out)
                    return
                if path == "/api/window":
                    event_window_id = _q1(q, "event_window_id", "")
                    if not event_window_id:
                        self._write_json({"error": "event_window_id is required"}, code=400)
                        return
                    self._write_json(state.one_window(event_window_id, limit=int(_q1(q, "limit", "2000"))))
                    return
                if path == "/api/files":
                    p = _q1(q, "path", str(state.samples_path.parent))
                    self._write_json(state.list_dir(p))
                    return
                if path == "/api/file":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    self._write_json(state.preview_file(p, rows=int(_q1(q, "rows", "20"))))
                    return
                if path == "/audio":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    self._write_bytes(state.read_audio_bytes(p), content_type="audio/wav", code=200)
                    return
                if path == "/spectrogram":
                    png = state.render_spectrogram_png(
                        path=_q1(q, "path", ""),
                        mel_shard_path=_q1(q, "mel_shard_path", ""),
                        mel_index=int(_q1(q, "mel_index", "0")),
                    )
                    self._write_bytes(png, content_type="image/png", code=200)
                    return
                self._write_json({"error": f"not found: {path}"}, code=404)
            except FileNotFoundError as exc:
                self._write_json({"error": str(exc)}, code=404)
            except PermissionError as exc:
                self._write_json({"error": str(exc)}, code=403)
            except Exception as exc:
                self._write_json({"error": str(exc)}, code=500)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def main() -> int:
    args = _arg_parser().parse_args()
    samples = Path(args.samples_parquet).expanduser().resolve()
    if not samples.exists():
        raise SystemExit(f"samples parquet not found: {samples}")
    roots = [Path(p).expanduser().resolve() for p in args.allow_root]
    if not roots:
        roots = _default_allowed_roots(samples)
    state = AppState(samples, roots)
    handler = make_handler(state)
    server = ThreadingHTTPServer((str(args.host), int(args.port)), handler)
    print(f"[ok] serving http://{args.host}:{args.port}", flush=True)
    print(f"[ok] samples={samples}", flush=True)
    print(f"[ok] allowed_roots={[str(r) for r in roots]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
