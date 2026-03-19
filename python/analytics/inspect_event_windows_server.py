#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cgi
import glob
import hashlib
import io
import json
import mimetypes
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

import matplotlib
import pandas as pd
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    import soundfile as sf  # type: ignore
except Exception:
    sf = None

try:
    from scipy.io import wavfile  # type: ignore
except Exception:
    wavfile = None


DEFAULT_DATA_ROOT = "/mnt/d/datasets/svwatergo"
DEFAULT_SAMPLES = (
    "/mnt/d/datasets/svwatergo/derived/"
    "dataset=audio_event_dataset/site=bluerock/window_s=10/samples.parquet"
)
DEFAULT_SAMPLES_GLOB = (
    "/mnt/d/datasets/svwatergo/derived/"
    "dataset=audio_event_dataset/site=*/window_s=10/samples.parquet"
)
DEFAULT_MODELS_DIR = DEFAULT_DATA_ROOT
DEFAULT_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "segment_inspector_uploads"
DEFAULT_UPLOAD_MODEL = (
    "/mnt/d/datasets/svwatergo/domain_matrix/source/checkpoints/"
    "train_bluerock__rpi_audio_auxsweep_1p0_ep15/audio_pretrained_embedding_multitask_best.pt"
)
DEFAULT_UPLOAD_MODEL_CANDIDATES = [
    DEFAULT_UPLOAD_MODEL,
    (
        "/mnt/d/datasets/svwatergo/domain_matrix/source/checkpoints/"
        "train_bluerock__rpi_audio_auxsweep_1.0/audio_pretrained_embedding_multitask_best.pt"
    ),
]
PARQUET_PRESETS = [
    (
        "Bluerock Camera 5 PCA",
        "/mnt/d/datasets/svwatergo/derived/plots/bluerock_camera5_actuation_embedding_pca.parquet",
    ),
    (
        "Bluerock Other Wyze PCA",
        "/mnt/d/datasets/svwatergo/derived_wyze_bluerock_other/plots/bluerock_other_actuation_embedding_pca.parquet",
    ),
    (
        "Pryor Farm Wyze PCA",
        "/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/plots/pryorfarm_actuation_embedding_pca.parquet",
    ),
    (
        "Santa Teresa Wyze PCA",
        "/mnt/d/datasets/svwatergo/derived_wyze_santateresa/plots/santateresa_actuation_embedding_pca.parquet",
    ),
]


def _dataset_super_root(path: Path) -> Optional[Path]:
    parts = list(path.resolve().parts)
    for i, part in enumerate(parts):
        if part == "svwatergo":
            return Path(*parts[: i + 1])
    return None


def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()

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
  <pre id="datasetStats" class="mono"></pre>
  <div style="margin:6px 0;">
    <a href="/parquet" target="_blank" rel="noopener">Open Parquet Query Page</a>
    |
    <a href="/upload" target="_blank" rel="noopener">Open Upload Inference Page</a>
    |
    <a href="#" onclick="loadDir(''); return false;">Browse Raw Dataset</a>
    |
    <a href="/raw/" target="_blank" rel="noopener">Open Static /raw/ Browser</a>
  </div>

  <div class="panel">
    <div class="row">
      <div><label>site</label><input id="site" value="" /></div>
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
        <th>event_window_id</th><th>site</th><th>split</th><th>class</th><th>segments</th><th>seconds</th><th>source</th><th>day</th><th>start</th><th>end</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <div><b>Selected Window</b>: <span id="selectedWindow" class="mono"></span></div>
    <table id="segmentsTbl">
      <thead><tr>
        <th>sample_id</th><th>start</th><th>end</th><th>class</th><th>states</th><th>mel_ok</th><th>audio</th><th>spec</th><th>infer</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <div><b>Segment Media</b>: <span id="mediaInfo" class="mono"></span></div>
    <div class="row" style="margin-top:8px;">
      <div style="min-width:55%">
        <label>model path</label>
        <input id="modelPath" style="width:100%" placeholder="/mnt/d/.../audio_pca_svm_model.joblib or .../audio_tiny_cnn_model.pt" />
      </div>
      <div style="min-width:30%">
        <label>checkpoint</label>
        <select id="modelSelect" style="width:100%"></select>
      </div>
      <div><label>&nbsp;</label><button onclick="loadModels()">Refresh Models</button></div>
      <div>
        <label>model kind</label>
        <select id="modelKind">
          <option value="auto">auto</option>
          <option value="multitask_panns">multitask_panns</option>
          <option value="pca_svm">pca_svm</option>
          <option value="tiny_cnn">tiny_cnn</option>
          <option value="frozen_embed_panns">frozen_embed_panns</option>
        </select>
      </div>
      <div><label>&nbsp;</label><button onclick="inferCurrent()">Infer Current</button></div>
    </div>
    <audio id="audioPlayer" controls style="width:100%; margin-top:8px;"></audio>
    <div style="margin-top:8px;">
      <img id="specImg" style="max-width:100%; border:1px solid #ddd;" />
    </div>
    <pre id="inferOut"></pre>
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
    <div><b>Parquet Query</b>: inspect arbitrary parquet rows and open their media</div>
    <div class="row">
      <div style="min-width:60%">
        <label>parquet path</label>
        <input id="parquetPath" style="width:100%" />
      </div>
      <div><label>rows</label><input id="parquetRows" type="number" value="25" /></div>
      <div><label>filter col</label><input id="parquetFilterCol" value="" /></div>
      <div><label>filter val</label><input id="parquetFilterVal" value="" /></div>
    </div>
    <div class="row">
      <div><label>pca1</label><input id="parquetPca1" value="" /></div>
      <div><label>pca2</label><input id="parquetPca2" value="" /></div>
      <div><label>pca3</label><input id="parquetPca3" value="" /></div>
      <div><label>display cols</label><input id="parquetCols" value="sample_id,segment_path,audio_source,split,actuation_trit,actuation_combo,pca1,pca2,pca3,dist2" style="width:420px" /></div>
      <div><label>&nbsp;</label><button onclick="queryParquet()">Query</button></div>
    </div>
    <table id="parquetTbl">
      <thead><tr><th>actions</th><th>summary</th></tr></thead>
      <tbody></tbody>
    </table>
    <pre id="parquetMetaPreview"></pre>
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
    `rows=${d.n_rows} windows=${d.n_windows} splits=${JSON.stringify(d.by_split)} sites=${JSON.stringify(d.by_site || {})}`;
  document.getElementById('datasetStats').textContent =
    "datasets:\\n" + JSON.stringify(d.datasets || [], null, 2);
  window.__defaultBrowseRoot = d.dataset_root || '';
  const modelEl = document.getElementById('modelPath');
  if (modelEl && !modelEl.value.trim() && d.default_models) {
    if (d.default_models.svm_exists) {
      modelEl.value = d.default_models.svm_path;
      document.getElementById('modelKind').value = 'pca_svm';
    } else if (d.default_models.tiny_cnn_exists) {
      modelEl.value = d.default_models.tiny_cnn_path;
      document.getElementById('modelKind').value = 'tiny_cnn';
    } else {
      modelEl.value = d.default_models.svm_path || d.default_models.tiny_cnn_path || '';
      document.getElementById('modelKind').value = 'auto';
    }
  }
  await loadModels();
}
async function loadModels() {
  const d = await jget('/api/models');
  const sel = document.getElementById('modelSelect');
  const modelEl = document.getElementById('modelPath');
  const current = (modelEl.value || '').trim();
  sel.innerHTML = '';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '-- select .pt checkpoint --';
  sel.appendChild(empty);
  for (const p of (d.models || [])) {
    const o = document.createElement('option');
    o.value = String(p);
    o.textContent = String(p).replace((d.root || ''), '').replace(/^\\//, '');
    if (current && current === o.value) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = () => {
    const v = (sel.value || '').trim();
    if (!v) return;
    modelEl.value = v;
    const vl = v.toLowerCase();
    if (vl.endsWith('.pt') || vl.endsWith('.pth')) {
      if (vl.includes('audio_pretrained_embedding_multitask') || vl.includes('auxsweep') || vl.includes('multitask')) {
        document.getElementById('modelKind').value = 'multitask_panns';
      } else {
        document.getElementById('modelKind').value = 'tiny_cnn';
      }
    } else if (vl.includes('frozen_mlp_head') || vl.endsWith('.joblib')) {
      if (vl.includes('frozen_mlp_head')) {
        document.getElementById('modelKind').value = 'frozen_embed_panns';
      } else {
        document.getElementById('modelKind').value = 'pca_svm';
      }
    } else {
      document.getElementById('modelKind').value = 'pca_svm';
    }
  };
}
function esc(x) { return String(x ?? ''); }
window.__currentAudioPath = '';
async function loadWindows() {
  const q = new URLSearchParams();
  const site = document.getElementById('site').value.trim();
  const split = document.getElementById('split').value.trim();
  const klass = document.getElementById('klass').value.trim();
  const source = document.getElementById('source').value.trim();
  const day = document.getElementById('day').value.trim();
  const minSeg = document.getElementById('minSeg').value.trim();
  const limit = document.getElementById('limit').value.trim();
  if (site) q.set('site', site);
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
    tr.innerHTML = `<td><a href="#" data-id="${esc(w.event_window_id)}">${esc(w.event_window_id)}</a></td><td>${esc(w.site || '')}</td>
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
      <td title="${esc(s.mel_status || '')}">${s.mel_ok ? 'yes' : 'no'}</td>
      <td><button data-audio="${audioPath}">Play</button></td>
      <td><button data-audio="${audioPath}" data-mel="${melPath}" data-mel-idx="${melIdx}">Spec</button></td>
      <td><button data-audio="${audioPath}" data-infer="1">Infer</button></td>`;
    tb.appendChild(tr);
  }
  for (const b of tb.querySelectorAll('button[data-audio]')) {
    b.onclick = (ev) => {
      const btn = ev.target;
      const path = btn.getAttribute('data-audio') || '';
      const mel = btn.getAttribute('data-mel') || '';
      const melIdx = btn.getAttribute('data-mel-idx') || '0';
      const doInfer = btn.getAttribute('data-infer') === '1';
      if (doInfer) {
        inferPath(path).catch(e => alert(e.message));
      } else if (btn.textContent === 'Play') {
        showAudio(path);
        showSpec(path, mel, melIdx);
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
  window.__currentAudioPath = path;
  document.getElementById('mediaInfo').textContent = `audio: ${path}`;
}
function showSpec(audioPath, melPath, melIdx) {
  const img = document.getElementById('specImg');
  let url = '';
  if (melPath) {
    url = '/spectrogram?mel_shard_path=' + encodeURIComponent(melPath) + '&mel_index=' + encodeURIComponent(melIdx || '0');
  } else {
    url = '/spectrogram?path=' + encodeURIComponent(audioPath) + '&mel_index=' + encodeURIComponent(melIdx || '0');
  }
  img.src = url;
  document.getElementById('mediaInfo').textContent = `spec: ${audioPath}`;
}
async function inferPath(path) {
  const model = document.getElementById('modelPath').value.trim();
  const kind = document.getElementById('modelKind').value;
  if (!model) throw new Error('model path is required');
  if (!path) throw new Error('audio path is required');
  const q = new URLSearchParams();
  q.set('path', path);
  q.set('model', model);
  q.set('model_kind', kind || 'auto');
  const d = await jget('/api/infer?' + q.toString());
  document.getElementById('inferOut').textContent = JSON.stringify(d, null, 2);
}
async function inferCurrent() {
  const p = window.__currentAudioPath || '';
  await inferPath(p);
}
async function loadFile() {
  const p = document.getElementById('filePath').value.trim();
  const rows = document.getElementById('fileRows').value.trim();
  if (!p) return;
  const d = await jget('/api/file?path=' + encodeURIComponent(p) + '&rows=' + encodeURIComponent(rows || '20'));
  document.getElementById('filePreview').textContent = JSON.stringify(d, null, 2);
}
async function queryParquet() {
  const path = document.getElementById('parquetPath').value.trim();
  const rows = document.getElementById('parquetRows').value.trim();
  const filterCol = document.getElementById('parquetFilterCol').value.trim();
  const filterVal = document.getElementById('parquetFilterVal').value.trim();
  const pca1 = document.getElementById('parquetPca1').value.trim();
  const pca2 = document.getElementById('parquetPca2').value.trim();
  const pca3 = document.getElementById('parquetPca3').value.trim();
  const cols = document.getElementById('parquetCols').value.trim();
  if (!path) return;
  const q = new URLSearchParams();
  q.set('path', path);
  q.set('rows', rows || '25');
  if (filterCol) q.set('filter_col', filterCol);
  if (filterVal) q.set('filter_val', filterVal);
  if (pca1) q.set('pca1', pca1);
  if (pca2) q.set('pca2', pca2);
  if (pca3) q.set('pca3', pca3);
  if (cols) q.set('display_cols', cols);
  const d = await jget('/api/parquet_query?' + q.toString());
  const tb = document.querySelector('#parquetTbl tbody');
  tb.innerHTML = '';
  for (const row of (d.rows || [])) {
    const audioPath = esc(row.segment_path || '');
    const melPath = esc(row.mel_shard_path || '');
    const melIdx = esc(row.mel_shard_local_index ?? 0);
    const summary = (d.display_cols || []).map(c => `${c}=${esc(row[c])}`).join(' | ');
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>
      <button data-audio="${audioPath}">Play</button>
      <button data-audio="${audioPath}" data-mel="${melPath}" data-mel-idx="${melIdx}">Spec</button>
      <button data-meta="1">Meta</button>
    </td><td class="mono">${summary}</td>`;
    tb.appendChild(tr);
    const buttons = tr.querySelectorAll('button');
    buttons[0].onclick = () => { showAudio(audioPath); showSpec(audioPath, melPath, melIdx); };
    buttons[1].onclick = () => { showSpec(audioPath, melPath, melIdx); };
    buttons[2].onclick = () => {
      document.getElementById('parquetMetaPreview').textContent = JSON.stringify(row, null, 2);
    };
  }
  document.getElementById('parquetMetaPreview').textContent = JSON.stringify(
    {path: d.path, total_rows: d.total_rows, rows_returned: (d.rows || []).length},
    null,
    2
  );
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

UPLOAD_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Segment Upload Inspector</title>
  <style>
    body { font-family: sans-serif; margin: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
    .panel { border: 1px solid #ddd; padding: 10px; margin-top: 12px; }
    label { font-size: 12px; color: #333; display:block; }
    input, select, button { padding: 6px; font-size: 13px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #ddd; padding: 6px; font-size: 12px; text-align: left; vertical-align: top; }
    th { background: #f3f3f3; position: sticky; top: 0; }
    pre { white-space: pre-wrap; font-size: 12px; max-height: 360px; overflow: auto; }
    .mono { font-family: monospace; }
    img { max-width: 100%; border: 1px solid #ddd; }
  </style>
</head>
<body>
  <h2>Segment Upload Inspector</h2>
  <div style="margin:6px 0;">
    <a href="/" rel="noopener">Open Event Window Inspector</a>
    |
    <a href="/parquet" rel="noopener">Open Parquet Query Page</a>
  </div>

  <div class="panel">
    <div class="row">
      <div style="min-width:36%">
        <label>audio file (`.wav` or `.webm`)</label>
        <input id="audioFile" type="file" accept=".wav,.wave,.webm,audio/*,video/webm" />
      </div>
      <div style="min-width:40%">
        <label>model path</label>
        <input id="modelPath" style="width:100%" />
      </div>
      <div style="min-width:22%">
        <label>checkpoint</label>
        <select id="modelSelect" style="width:100%"></select>
      </div>
    </div>
    <div class="row">
      <div>
        <label>model kind</label>
        <select id="modelKind">
          <option value="auto">auto</option>
          <option value="multitask_panns">multitask_panns</option>
          <option value="frozen_embed_panns">frozen_embed_panns</option>
          <option value="tiny_cnn">tiny_cnn</option>
          <option value="pca_svm">pca_svm</option>
        </select>
      </div>
      <div>
        <label>window seconds</label>
        <input id="windowSeconds" type="number" step="0.5" min="0.5" value="10" />
      </div>
      <div><label>&nbsp;</label><button onclick="loadModels()">Refresh Models</button></div>
      <div><label>&nbsp;</label><button onclick="runUploadInfer()">Upload + Infer</button></div>
    </div>
    <pre id="status" class="mono"></pre>
  </div>

  <div class="panel">
    <div><b>Normalized Audio</b>: <span id="audioInfo" class="mono"></span></div>
    <audio id="audioPlayer" controls style="width:100%; margin-top:8px;"></audio>
  </div>

  <div class="panel">
    <div><b>Waveform + Spectrogram</b></div>
    <img id="plotImg" />
  </div>

  <div class="panel">
    <div><b>Window Predictions</b></div>
    <table id="predTbl">
      <thead><tr>
        <th>window</th><th>start_s</th><th>end_s</th><th>label</th><th>confidence</th><th>states</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="panel">
    <div><b>Raw Output</b></div>
    <pre id="rawOut"></pre>
  </div>

<script>
async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}
function esc(x) { return String(x ?? ''); }
function chooseKindFromPath(v) {
  const s = String(v || '').toLowerCase();
  if (!s) return 'auto';
  if (s.includes('audio_pretrained_embedding_multitask') || s.includes('auxsweep') || s.includes('multitask')) return 'multitask_panns';
  if (s.includes('frozen_mlp_head')) return 'frozen_embed_panns';
  if (s.endsWith('.pt') || s.endsWith('.pth')) return 'tiny_cnn';
  return 'pca_svm';
}
async function loadDefaults() {
  const d = await jget('/api/summary');
  const modelEl = document.getElementById('modelPath');
  const kindEl = document.getElementById('modelKind');
  const pref = ((d.default_models || {}).preferred_upload_model || '').trim();
  if (!modelEl.value.trim() && pref) {
    modelEl.value = pref;
    kindEl.value = chooseKindFromPath(pref);
  }
  await loadModels();
}
async function loadModels() {
  const d = await jget('/api/models');
  const sel = document.getElementById('modelSelect');
  const modelEl = document.getElementById('modelPath');
  const current = (modelEl.value || '').trim();
  sel.innerHTML = '';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '-- select checkpoint --';
  sel.appendChild(empty);
  for (const p of (d.models || [])) {
    const o = document.createElement('option');
    o.value = String(p);
    o.textContent = String(p).replace((d.root || ''), '').replace(/^\\//, '');
    if (current && current === o.value) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = () => {
    const v = (sel.value || '').trim();
    if (!v) return;
    modelEl.value = v;
    document.getElementById('modelKind').value = chooseKindFromPath(v);
  };
}
function renderPredictions(rows) {
  const tb = document.querySelector('#predTbl tbody');
  tb.innerHTML = '';
  for (const row of (rows || [])) {
    const stateText = Array.isArray(row.states) ? row.states.map((s) =>
      `${esc(s.name)}=${esc(s.predicted_state ?? s.predicted ?? '')} (p=${Number(s.probability_on ?? s.probability ?? 0).toFixed(3)}, c=${Number(s.confidence ?? 0).toFixed(3)})`
    ).join(' | ') : '';
    const conf = row.pred_confidence_mean ?? row.pred_confidence ?? row.confidence ?? '';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${esc(row.window_index)}</td>
      <td>${esc(row.start_sec)}</td>
      <td>${esc(row.end_sec)}</td>
      <td class="mono">${esc(row.pred_label || row.prediction_label || '')}</td>
      <td>${conf === '' ? '' : Number(conf).toFixed(3)}</td>
      <td class="mono">${esc(stateText)}</td>`;
    tb.appendChild(tr);
  }
}
async function runUploadInfer() {
  const fileEl = document.getElementById('audioFile');
  const model = document.getElementById('modelPath').value.trim();
  const kind = document.getElementById('modelKind').value;
  const windowSeconds = document.getElementById('windowSeconds').value.trim();
  const file = fileEl.files && fileEl.files[0];
  if (!file) throw new Error('select an audio file first');
  if (!model) throw new Error('model path is required');
  document.getElementById('status').textContent = 'uploading + running inference...';
  const fd = new FormData();
  fd.append('audio', file);
  fd.append('model', model);
  fd.append('model_kind', kind || 'auto');
  fd.append('window_seconds', windowSeconds || '10');
  const r = await fetch('/api/upload_infer', { method: 'POST', body: fd });
  if (!r.ok) throw new Error(await r.text());
  const d = await r.json();
  document.getElementById('status').textContent =
    `normalized=${esc((d.normalized_audio || {}).path || '')} windows=${esc(d.n_windows || 0)} effective_window_s=${esc(d.effective_window_seconds || '')}`;
  document.getElementById('audioInfo').textContent = esc((d.normalized_audio || {}).path || '');
  document.getElementById('audioPlayer').src = esc(d.normalized_audio_url || '');
  document.getElementById('plotImg').src = esc(d.plot_png_url || '');
  renderPredictions(d.windows || []);
  document.getElementById('rawOut').textContent = JSON.stringify(d, null, 2);
}
loadDefaults().catch(e => { document.getElementById('status').textContent = e.message; });
</script>
</body>
</html>
"""

PARQUET_QUERY_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Parquet Query Inspector</title>
  <style>
    body { font-family: sans-serif; margin: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
    label { font-size: 12px; color: #333; display:block; }
    input, button { padding: 6px; font-size: 13px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid #ddd; padding: 6px; font-size: 12px; text-align: left; vertical-align: top; }
    th { background: #f3f3f3; position: sticky; top: 0; }
    .panel { border: 1px solid #ddd; padding: 10px; margin-top: 12px; }
    pre { white-space: pre-wrap; font-size: 12px; max-height: 320px; overflow: auto; }
    .mono { font-family: monospace; }
  </style>
</head>
<body>
  <h2>Parquet Query Inspector</h2>
  <div style="margin:6px 0;">
    <a href="/" rel="noopener">Open Event Window Inspector</a>
  </div>
  <div class="panel">
    <div><b>Presets</b></div>
    <div class="row">
      <button onclick="usePreset('/mnt/d/datasets/svwatergo/derived/plots/bluerock_camera5_actuation_embedding_pca.parquet')">Bluerock Camera 5 PCA</button>
      <button onclick="usePreset('/mnt/d/datasets/svwatergo/derived_wyze_bluerock_other/plots/bluerock_other_actuation_embedding_pca.parquet')">Bluerock Other Wyze PCA</button>
      <button onclick="usePreset('/mnt/d/datasets/svwatergo/derived_wyze_pryorfarm/plots/pryorfarm_actuation_embedding_pca.parquet')">Pryor Farm Wyze PCA</button>
      <button onclick="usePreset('/mnt/d/datasets/svwatergo/derived_wyze_santateresa/plots/santateresa_actuation_embedding_pca.parquet')">Santa Teresa Wyze PCA</button>
    </div>
  </div>

  <div class="panel">
    <div class="row">
      <div style="min-width:60%">
        <label>parquet path</label>
        <input id="parquetPath" style="width:100%" />
      </div>
      <div><label>rows</label><input id="parquetRows" type="number" value="25" /></div>
      <div><label>filter col</label><input id="parquetFilterCol" value="" /></div>
      <div><label>filter val</label><input id="parquetFilterVal" value="" /></div>
    </div>
    <div class="row">
      <div><label>pca1</label><input id="parquetPca1" value="" /></div>
      <div><label>pca2</label><input id="parquetPca2" value="" /></div>
      <div><label>pca3</label><input id="parquetPca3" value="" /></div>
      <div><label>display cols</label><input id="parquetCols" value="sample_id,segment_path,audio_source,split,actuation_trit,actuation_combo,pca1,pca2,pca3,dist2" style="width:420px" /></div>
      <div><label>&nbsp;</label><button onclick="queryParquet()">Query</button></div>
    </div>
    <table id="parquetTbl">
      <thead><tr><th>actions</th><th>summary</th></tr></thead>
      <tbody></tbody>
    </table>
    <pre id="parquetMetaPreview"></pre>
  </div>

  <div class="panel">
    <div><b>Segment Media</b>: <span id="mediaInfo" class="mono"></span></div>
    <audio id="audioPlayer" controls style="width:100%; margin-top:8px;"></audio>
    <div style="margin-top:8px;">
      <img id="specImg" style="max-width:100%; border:1px solid #ddd;" />
    </div>
    <pre id="rowMeta"></pre>
  </div>

<script>
async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}
function esc(x) { return String(x ?? ''); }
function usePreset(path) {
  document.getElementById('parquetPath').value = path;
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
    url = '/spectrogram?path=' + encodeURIComponent(audioPath) + '&mel_index=' + encodeURIComponent(melIdx || '0');
  }
  img.src = url;
  document.getElementById('mediaInfo').textContent = `spec: ${audioPath}`;
}
async function queryParquet() {
  const path = document.getElementById('parquetPath').value.trim();
  const rows = document.getElementById('parquetRows').value.trim();
  const filterCol = document.getElementById('parquetFilterCol').value.trim();
  const filterVal = document.getElementById('parquetFilterVal').value.trim();
  const pca1 = document.getElementById('parquetPca1').value.trim();
  const pca2 = document.getElementById('parquetPca2').value.trim();
  const pca3 = document.getElementById('parquetPca3').value.trim();
  const cols = document.getElementById('parquetCols').value.trim();
  if (!path) return;
  const q = new URLSearchParams();
  q.set('path', path);
  q.set('rows', rows || '25');
  if (filterCol) q.set('filter_col', filterCol);
  if (filterVal) q.set('filter_val', filterVal);
  if (pca1) q.set('pca1', pca1);
  if (pca2) q.set('pca2', pca2);
  if (pca3) q.set('pca3', pca3);
  if (cols) q.set('display_cols', cols);
  const d = await jget('/api/parquet_query?' + q.toString());
  const tb = document.querySelector('#parquetTbl tbody');
  tb.innerHTML = '';
  for (const row of (d.rows || [])) {
    const audioPath = esc(row.segment_path || '');
    const melPath = esc(row.mel_shard_path || '');
    const melIdx = esc(row.mel_shard_local_index ?? 0);
    const summary = (d.display_cols || []).map(c => `${c}=${esc(row[c])}`).join(' | ');
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>
      <button data-audio="${audioPath}">Play</button>
      <button data-audio="${audioPath}" data-mel="${melPath}" data-mel-idx="${melIdx}">Spec</button>
      <button data-meta="1">Meta</button>
    </td><td class="mono">${summary}</td>`;
    tb.appendChild(tr);
    const buttons = tr.querySelectorAll('button');
    buttons[0].onclick = () => { showAudio(audioPath); showSpec(audioPath, melPath, melIdx); };
    buttons[1].onclick = () => { showSpec(audioPath, melPath, melIdx); };
    buttons[2].onclick = () => {
      document.getElementById('rowMeta').textContent = JSON.stringify(row, null, 2);
    };
  }
  document.getElementById('parquetMetaPreview').textContent = JSON.stringify(
    {path: d.path, total_rows: d.total_rows, rows_returned: (d.rows || []).length},
    null,
    2
  );
}
(() => {
  const q = new URLSearchParams(window.location.search);
  const p = q.get('path') || '';
  if (p) document.getElementById('parquetPath').value = p;
})();
</script>
</body>
</html>
"""


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Basic web inspector for event windows and raw dataset files.")
    p.add_argument(
        "--samples-parquet",
        action="append",
        default=[],
        help="Samples parquet path (repeatable). If omitted, defaults to bluerock sample.",
    )
    p.add_argument(
        "--samples-glob",
        default="",
        help="Optional glob for samples parquet files (e.g. dataset=audio_event_dataset/site=*/window_s=10/samples.parquet)",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Allowed root for /api/file and /api/files (repeatable). Defaults to parent of samples parquet.",
    )
    p.add_argument(
        "--models-dir",
        default=DEFAULT_MODELS_DIR,
        help="Directory to recursively scan for .pt model checkpoints.",
    )
    return p


def _default_allowed_roots(samples_paths: List[Path]) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for samples in samples_paths:
        cand = samples.parent
        for parent in samples.parents:
            if parent.name == "derived":
                cand = parent
                break
        c = cand.resolve()
        if str(c) not in seen:
            seen.add(str(c))
            out.append(c)
        parent = c.parent
        try:
            siblings = sorted(
                [p.resolve() for p in parent.iterdir() if p.is_dir() and p.name.startswith("derived")],
                key=lambda p: p.name.lower(),
            )
        except Exception:
            siblings = []
        for sib in siblings:
            if str(sib) not in seen:
                seen.add(str(sib))
                out.append(sib)
    return out


def _infer_site_from_samples_path(samples_path: Path) -> str:
    for part in samples_path.parts:
        if part.startswith("site="):
            return part.split("=", 1)[1].strip().lower()
    return ""


def _build_root_aliases(roots: List[Path]) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    used: Dict[str, int] = {}
    for root in roots:
        base = root.name or "root"
        idx = used.get(base, 0)
        alias = base if idx == 0 else f"{base}_{idx + 1}"
        used[base] = idx + 1
        out[alias] = root
    return out


class AppState:
    def __init__(self, samples_paths: List[Path], allowed_roots: List[Path], models_dir: Path, upload_root: Path) -> None:
        self.samples_paths = [p.resolve() for p in samples_paths]
        self.models_dir = models_dir
        self.upload_root = upload_root.resolve()
        self.upload_root.mkdir(parents=True, exist_ok=True)
        roots = [p.resolve() for p in allowed_roots]
        if self.models_dir.exists() and all(self.models_dir.resolve() != r for r in roots):
            roots.append(self.models_dir.resolve())
        if all(self.upload_root != r for r in roots):
            roots.append(self.upload_root)
        self.allowed_roots = roots
        self.allowed_root_aliases = _build_root_aliases(self.allowed_roots)
        if not self.samples_paths:
            raise ValueError("No samples parquet files provided.")
        dfs: List[pd.DataFrame] = []
        for sp in self.samples_paths:
            dfi = pd.read_parquet(sp)
            if "site" not in dfi.columns:
                dfi["site"] = _infer_site_from_samples_path(sp)
            else:
                dfi["site"] = dfi["site"].astype("string").fillna("").str.strip().str.lower()
            dfi["__samples_path"] = str(sp)
            dfs.append(dfi)
        self.df = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
        required = [
            "event_window_id",
            "site",
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
                site=("site", "first"),
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
        # Keep datetime sort keys for API ordering, then cast for JSON output.
        g = g.sort_values(["site", "day_utc", "start_ts", "event_window_id"], ascending=[True, True, True, True]).reset_index(drop=True)
        g["start_ts"] = g["start_ts"].astype("string")
        g["end_ts"] = g["end_ts"].astype("string")
        return g

    def summary(self) -> Dict[str, Any]:
        by_split = self.df["split"].astype("string").value_counts(dropna=False).to_dict()
        by_class = self.df["primary_class"].astype("string").value_counts(dropna=False).to_dict()
        by_site = self.df["site"].astype("string").value_counts(dropna=False).to_dict()
        datasets: List[Dict[str, Any]] = []
        for src_path, dsi in self.df.groupby("__samples_path", dropna=False):
            dsite = dsi["site"].astype("string").value_counts(dropna=False).to_dict()
            dsplit = dsi["split"].astype("string").value_counts(dropna=False).to_dict()
            dclass = dsi["primary_class"].astype("string").value_counts(dropna=False).to_dict()
            dsource = dsi["audio_source"].astype("string").value_counts(dropna=False).to_dict()
            datasets.append(
                {
                    "samples_parquet": str(src_path),
                    "n_rows": int(len(dsi)),
                    "n_windows": int(dsi["event_window_id"].nunique(dropna=True)),
                    "by_site": {str(k): int(v) for k, v in dsite.items()},
                    "by_split": {str(k): int(v) for k, v in dsplit.items()},
                    "by_class": {str(k): int(v) for k, v in dclass.items()},
                    "by_source": {str(k): int(v) for k, v in dsource.items()},
                }
            )
        datasets = sorted(datasets, key=lambda x: str(x.get("samples_parquet", "")))
        derived_root = self.allowed_roots[0]
        svm_model = derived_root / "checkpoints" / "bluerock_10s_svm_ropumprun" / "audio_pca_svm_model.joblib"
        tiny_model = derived_root / "checkpoints" / "bluerock_10s_tiny_cnn_ropumprun" / "audio_tiny_cnn_model.pt"
        multitask_model = self._resolve_default_upload_model()
        return {
            "samples_parquet": str(self.samples_paths[0]),
            "samples_parquets": [str(p) for p in self.samples_paths],
            "dataset_root": str(derived_root),
            "n_rows": int(len(self.df)),
            "n_windows": int(self.df["event_window_id"].nunique(dropna=True)),
            "by_split": {str(k): int(v) for k, v in by_split.items()},
            "by_class": {str(k): int(v) for k, v in by_class.items()},
            "by_site": {str(k): int(v) for k, v in by_site.items()},
            "datasets": datasets,
            "default_models": {
                "svm_path": str(svm_model),
                "svm_exists": bool(svm_model.exists()),
                "tiny_cnn_path": str(tiny_model),
                "tiny_cnn_exists": bool(tiny_model.exists()),
                "multitask_path": str(multitask_model),
                "multitask_exists": bool(multitask_model.exists()),
                "preferred_upload_model": str(multitask_model),
            },
            "models_dir": str(self.models_dir),
            "upload_root": str(self.upload_root),
        }

    def list_models(self, *, limit: int = 1000) -> Dict[str, Any]:
        root = self._check_allowed(str(self.models_dir))
        if not root.exists():
            return {"root": str(root), "models": []}
        paths = [p for p in root.rglob("*.pt") if p.is_file()]
        paths += [p for p in root.rglob("*.pth") if p.is_file()]
        paths += [p for p in root.rglob("*.joblib") if p.is_file()]
        preferred = self._resolve_default_upload_model().resolve()

        def _sort_key(p: Path) -> Any:
            try:
                is_pref = int(p.resolve() == preferred)
            except Exception:
                is_pref = 0
            try:
                mtime = float(p.stat().st_mtime)
            except Exception:
                mtime = 0.0
            return (-is_pref, -mtime, str(p))

        paths.sort(key=_sort_key)
        models = [str(p) for p in paths[: max(1, min(int(limit), 5000))]]
        return {"root": str(root), "models": models}

    def windows(
        self,
        *,
        site: str = "",
        split: str = "",
        primary_class: str = "",
        audio_source: str = "",
        day_utc: str = "",
        min_segments: int = 1,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        out = self._windows_df
        if site:
            out = out[out["site"].astype("string") == site]
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
            "mel_shard_local_index",
            "window_seconds",
            "overlap_s_producing",
            "overlap_s_delivering",
            "overlap_s_flushing",
            "overlap_s_quiet",
            "states_seen",
        ]
        cols = [c for c in keep_cols if c in out.columns]
        out = out[cols].head(max(1, min(int(limit), 10000))).copy()
        mel_shape_cache: Dict[str, Any] = {}
        mel_ok: List[bool] = []
        mel_status: List[str] = []
        for row in out.itertuples(index=False):
            mpath = getattr(row, "mel_shard_path", None)
            midx_raw = getattr(row, "mel_shard_local_index", None)
            if not isinstance(mpath, str) or not mpath.strip():
                mel_ok.append(False)
                mel_status.append("missing_mel_path")
                continue
            try:
                p = self._check_allowed(mpath)
            except Exception:
                mel_ok.append(False)
                mel_status.append("path_not_allowed")
                continue
            if not p.exists():
                mel_ok.append(False)
                mel_status.append("missing_shard")
                continue
            p_str = str(p)
            if p_str not in mel_shape_cache:
                try:
                    with np.load(p, mmap_mode="r") as data:
                        key = "mel" if "mel" in data.files else ("arr_0" if "arr_0" in data.files else data.files[0])
                        arr = data[key]
                        mel_shape_cache[p_str] = tuple(int(x) for x in arr.shape)
                except Exception:
                    mel_shape_cache[p_str] = None
            shape = mel_shape_cache[p_str]
            if shape is None:
                mel_ok.append(False)
                mel_status.append("unreadable_shard")
                continue
            try:
                midx = int(midx_raw)
            except Exception:
                mel_ok.append(False)
                mel_status.append("invalid_index")
                continue
            if len(shape) == 3:
                ok = 0 <= midx < int(shape[0])
            elif len(shape) == 2:
                ok = (midx == 0)
            else:
                ok = False
            mel_ok.append(bool(ok))
            mel_status.append("ok" if ok else f"index_oob shape={shape}")
        out["mel_ok"] = mel_ok
        out["mel_status"] = mel_status
        for c in ["segment_start_ts_utc", "segment_end_ts_utc"]:
            if c in out.columns:
                out[c] = out[c].astype("string")
        return {"event_window_id": event_window_id, "total_segments": total, "segments": out.to_dict(orient="records")}

    def read_audio_bytes(self, path: str) -> bytes:
        p = self._check_allowed(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        return p.read_bytes()

    def infer_audio(self, *, path: str, model: str, model_kind: str = "auto") -> Dict[str, Any]:
        wav_p = self._check_allowed(path)
        model_p = self._check_allowed(model)
        if not wav_p.exists():
            raise FileNotFoundError(str(wav_p))
        if not model_p.exists():
            raise FileNotFoundError(str(model_p))

        kind = self._resolve_model_kind(model_p=model_p, requested_kind=model_kind)

        if kind == "multitask_panns":
            pred = self._infer_multitask_audio_windows(
                model_path=model_p,
                wav_path=wav_p,
                window_seconds=10.0,
            )
        elif kind == "tiny_cnn":
            from python.ml.train.audio_tiny_cnn import predict_audio_tiny_cnn  # type: ignore

            pred = predict_audio_tiny_cnn(model_path=model_p, wav_path=wav_p)
        elif kind == "frozen_embed_panns":
            from python.ml.train.audio_pretrained_embeddings import predict_audio_pretrained_frozen_head  # type: ignore

            pred = predict_audio_pretrained_frozen_head(model_path=model_p, wav_path=wav_p)
        else:
            from python.ml.train.audio_pca_svm import predict_audio_pca_svm  # type: ignore

            pred = predict_audio_pca_svm(model_path=model_p, wav_path=wav_p)

        stats: Dict[str, Any] = {"path": str(wav_p), "size_bytes": int(wav_p.stat().st_size)}
        try:
            with wave.open(str(wav_p), "rb") as wf:
                n_channels = int(wf.getnchannels())
                sample_rate = int(wf.getframerate())
                n_frames = int(wf.getnframes())
                sampwidth = int(wf.getsampwidth())
            stats.update(
                {
                    "sample_rate": sample_rate,
                    "n_channels": n_channels,
                    "n_frames": n_frames,
                    "sample_width_bytes": sampwidth,
                    "duration_sec": (float(n_frames) / float(sample_rate) if sample_rate > 0 else None),
                }
            )
        except Exception:
            pass

        return {
            "model": str(model_p),
            "model_kind": kind,
            "audio_stats": stats,
            "prediction": pred,
        }

    def infer_uploaded_audio(
        self,
        *,
        upload_name: str,
        upload_bytes: bytes,
        model: str,
        model_kind: str = "auto",
        window_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        model_p = self._check_allowed(model)
        if not model_p.exists():
            raise FileNotFoundError(str(model_p))
        kind = self._resolve_model_kind(model_p=model_p, requested_kind=model_kind)
        job_dir = self._make_upload_job_dir()
        src_name = _sanitize_upload_name(upload_name or "upload.bin")
        src_path = job_dir / src_name
        src_path.write_bytes(upload_bytes)
        normalized_wav = job_dir / f"{src_path.stem}_normalized.wav"
        _convert_to_wav_ffmpeg(src=src_path, dst=normalized_wav, sample_rate=32000, channels=1, pcm_codec="pcm_s16le")
        plot_path = job_dir / f"{normalized_wav.stem}_wave_spec.png"
        y, sr = _load_wav_for_spec(normalized_wav)
        plot_path.write_bytes(_plot_waveform_and_spectrogram_png(y, sample_rate=sr, title=src_name))

        effective_window_seconds = float(window_seconds)
        if kind in {"pca_svm", "tiny_cnn", "frozen_embed_panns"}:
            effective_window_seconds = self._model_target_seconds(model_p=model_p, kind=kind, fallback=float(window_seconds))

        if kind == "multitask_panns":
            pred = self._infer_multitask_audio_windows(
                model_path=model_p,
                wav_path=normalized_wav,
                window_seconds=effective_window_seconds,
            )
        else:
            pred = self._infer_classic_audio_windows(
                model_path=model_p,
                wav_path=normalized_wav,
                model_kind=kind,
                window_seconds=effective_window_seconds,
                scratch_dir=job_dir / "segments",
            )

        return {
            "input": {
                "filename": src_name,
                "size_bytes": int(len(upload_bytes)),
                "content_hash": hashlib.sha1(upload_bytes).hexdigest(),
                "path": str(src_path),
            },
            "normalized_audio": pred.pop("normalized_audio", self._audio_file_stats(normalized_wav)),
            "normalized_audio_url": f"/audio?path={quote(str(normalized_wav))}",
            "plot_png": {
                "path": str(plot_path),
                "size_bytes": int(plot_path.stat().st_size),
            },
            "plot_png_url": f"/image?path={quote(str(plot_path))}",
            "model": str(model_p),
            "model_kind": kind,
            "effective_window_seconds": float(effective_window_seconds),
            **pred,
        }

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
        y, rate = _load_wav_for_spec(wav_p)
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

    def _make_upload_job_dir(self) -> Path:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = self.upload_root / f"{stamp}_{uuid.uuid4().hex[:10]}"
        out.mkdir(parents=True, exist_ok=False)
        return out

    def _resolve_default_upload_model(self) -> Path:
        for cand in DEFAULT_UPLOAD_MODEL_CANDIDATES:
            p = Path(cand).expanduser().resolve()
            if p.exists():
                return p
        if self.models_dir.exists():
            for patt in ("audio_pretrained_embedding_multitask_best.pt", "*.pt", "*.pth", "*.joblib"):
                for p in self.models_dir.rglob(patt):
                    if not p.is_file():
                        continue
                    name_l = p.name.lower()
                    path_l = str(p).lower()
                    if "bluerock" in path_l and ("rpi_audio" in path_l or "auxsweep" in path_l or "multitask" in name_l):
                        return p.resolve()
            for patt in ("audio_pretrained_embedding_multitask_best.pt", "*.pt", "*.pth", "*.joblib"):
                for p in self.models_dir.rglob(patt):
                    if p.is_file():
                        return p.resolve()
        return Path(DEFAULT_UPLOAD_MODEL).expanduser().resolve()

    def _resolve_model_kind(self, *, model_p: Path, requested_kind: str) -> str:
        kind = str(requested_kind or "auto").strip().lower()
        allowed = {"auto", "pca_svm", "tiny_cnn", "frozen_embed_panns", "multitask_panns"}
        if kind not in allowed:
            raise ValueError("model_kind must be one of auto, pca_svm, tiny_cnn, frozen_embed_panns, multitask_panns")
        if kind != "auto":
            return kind
        name_l = model_p.name.lower()
        path_l = str(model_p).lower()
        if "audio_pretrained_embedding_multitask" in name_l or "auxsweep" in path_l or "multitask" in path_l:
            return "multitask_panns"
        if "frozen_mlp_head" in name_l:
            return "frozen_embed_panns"
        if model_p.suffix.lower() in (".pt", ".pth"):
            return "tiny_cnn"
        return "pca_svm"

    def _model_target_seconds(self, *, model_p: Path, kind: str, fallback: float) -> float:
        try:
            if kind == "pca_svm":
                from python.ml.train.audio_pca_svm import load_audio_pca_svm_bundle  # type: ignore

                bundle = load_audio_pca_svm_bundle(model_p)
                return float((bundle.get("mel_config") or {}).get("target_seconds", fallback))
            if kind == "tiny_cnn":
                from python.ml.train.audio_tiny_cnn import load_audio_tiny_cnn_bundle  # type: ignore

                bundle = load_audio_tiny_cnn_bundle(model_p)
                return float((bundle.get("mel_config") or {}).get("target_seconds", fallback))
            if kind == "frozen_embed_panns":
                from python.ml.train.audio_pretrained_embeddings import load_frozen_pretrained_embedding_head  # type: ignore

                bundle = load_frozen_pretrained_embedding_head(model_p)
                return float(bundle.get("target_seconds", fallback))
        except Exception:
            return float(fallback)
        return float(fallback)

    def _audio_file_stats(self, path: Path) -> Dict[str, Any]:
        stats: Dict[str, Any] = {"path": str(path), "size_bytes": int(path.stat().st_size)}
        try:
            with wave.open(str(path), "rb") as wf:
                sample_rate = int(wf.getframerate())
                n_channels = int(wf.getnchannels())
                n_frames = int(wf.getnframes())
                sample_width = int(wf.getsampwidth())
            stats.update(
                {
                    "sample_rate": sample_rate,
                    "n_channels": n_channels,
                    "n_frames": n_frames,
                    "sample_width_bytes": sample_width,
                    "duration_sec": (float(n_frames) / float(sample_rate) if sample_rate > 0 else None),
                }
            )
        except Exception:
            pass
        return stats

    def _infer_classic_audio_windows(
        self,
        *,
        model_path: Path,
        wav_path: Path,
        model_kind: str,
        window_seconds: float,
        scratch_dir: Path,
    ) -> Dict[str, Any]:
        y, sr = _load_wav_for_spec(wav_path)
        if y.size == 0:
            raise ValueError("empty normalized wav")
        window_n = max(1, int(round(float(window_seconds) * float(sr))))
        scratch_dir.mkdir(parents=True, exist_ok=True)
        windows: List[Dict[str, Any]] = []
        total_samples = int(y.shape[0])
        n_windows = int(np.ceil(float(total_samples) / float(window_n)))
        for idx in range(n_windows):
            i0 = idx * window_n
            i1 = min(total_samples, i0 + window_n)
            chunk = np.asarray(y[i0:i1], dtype=np.float32)
            padded = np.zeros((window_n,), dtype=np.float32)
            padded[: len(chunk)] = chunk
            seg_path = scratch_dir / f"window_{idx:04d}.wav"
            _write_wav_pcm16(seg_path, padded, sample_rate=int(sr))
            if model_kind == "tiny_cnn":
                from python.ml.train.audio_tiny_cnn import predict_audio_tiny_cnn  # type: ignore

                pred = predict_audio_tiny_cnn(model_path=model_path, wav_path=seg_path)
            elif model_kind == "frozen_embed_panns":
                from python.ml.train.audio_pretrained_embeddings import predict_audio_pretrained_frozen_head  # type: ignore

                pred = predict_audio_pretrained_frozen_head(model_path=model_path, wav_path=seg_path)
            else:
                from python.ml.train.audio_pca_svm import predict_audio_pca_svm  # type: ignore

                pred = predict_audio_pca_svm(model_path=model_path, wav_path=seg_path)
            windows.append(
                {
                    "window_index": int(idx),
                    "start_sec": round(float(i0) / float(sr), 3),
                    "end_sec": round(float(i1) / float(sr), 3),
                    "duration_sec": round(float(i1 - i0) / float(sr), 3),
                    "padded_duration_sec": round(float(window_n) / float(sr), 3),
                    **_summarize_classic_prediction(pred),
                }
            )
        return {
            "normalized_audio": self._audio_file_stats(wav_path),
            "n_windows": int(len(windows)),
            "windows": windows,
        }

    def _infer_multitask_audio_windows(
        self,
        *,
        model_path: Path,
        wav_path: Path,
        window_seconds: float,
    ) -> Dict[str, Any]:
        try:
            import torch  # type: ignore
            from scipy import signal  # type: ignore
        except Exception as e:
            raise RuntimeError("Missing torch/scipy for multitask inference") from e

        from python.ml.storage.audio import read_audio_path_ffmpeg  # type: ignore
        from python.ml.train.audio_pretrained_embedding_multitask import AudioPretrainedEmbeddingMultitaskModelFactory  # type: ignore
        from python.ml.train.audio_pretrained_embeddings import _PannsBackend  # type: ignore

        ckpt = torch.load(str(model_path), map_location="cpu")
        if not isinstance(ckpt, dict) or "state_dict" not in ckpt:
            raise ValueError(f"Invalid multitask checkpoint: {model_path}")
        task_mode = str(ckpt.get("task_mode", "multiclass")).strip().lower()
        if task_mode not in {"multiclass", "multilabel", "multiregression"}:
            raise ValueError(f"Unsupported multitask task_mode: {task_mode}")

        y, sr, _subtype = read_audio_path_ffmpeg(wav_path, sample_rate=32000, mono=True)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if y.size == 0:
            raise ValueError("empty normalized wav")
        target_sr = 32000
        if int(sr) != int(target_sr):
            y = signal.resample_poly(y, int(target_sr), int(sr)).astype(np.float32, copy=False)
            sr = int(target_sr)

        window_n = max(1, int(round(float(window_seconds) * float(sr))))
        total_samples = int(y.shape[0])
        n_windows = int(np.ceil(float(total_samples) / float(window_n)))
        chunks = np.zeros((n_windows, window_n), dtype=np.float32)
        chunk_meta: List[Dict[str, Any]] = []
        for idx in range(n_windows):
            i0 = idx * window_n
            i1 = min(total_samples, i0 + window_n)
            clip = np.asarray(y[i0:i1], dtype=np.float32)
            chunks[idx, : len(clip)] = clip
            chunk_meta.append(
                {
                    "window_index": int(idx),
                    "start_sec": round(float(i0) / float(sr), 3),
                    "end_sec": round(float(i1) / float(sr), 3),
                    "duration_sec": round(float(i1 - i0) / float(sr), 3),
                    "padded_duration_sec": round(float(window_n) / float(sr), 3),
                }
            )

        backend = _PannsBackend(device=("cuda" if torch.cuda.is_available() else "cpu"))
        emb = backend.extract_embedding_np(chunks)
        hidden = [int(v) for v in (ckpt.get("hidden") or [])]
        z_dim = int(ckpt.get("z_dim", 64))
        input_dim = int(ckpt.get("input_dim", int(emb.shape[1])))
        y_dim = int(ckpt.get("n_targets", 0))
        model = AudioPretrainedEmbeddingMultitaskModelFactory.build(
            in_dim=input_dim,
            hidden=hidden,
            z_dim=z_dim,
            y_dim=y_dim,
            plc_dim=0,
            drop=0.0,
        )
        model.load_state_dict(ckpt["state_dict"], strict=False)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)
        model.eval()
        x = torch.from_numpy(np.asarray(emb, dtype=np.float32)).to(device)
        with torch.no_grad():
            logits, z_latent, _ = model(x)

        rows: List[Dict[str, Any]] = []
        class_names = [str(v) for v in (ckpt.get("class_names") or [])]
        target_cols = [str(v) for v in (ckpt.get("target_cols") or []) if str(v).strip()]
        thresholds = np.asarray(
            list(ckpt.get("inference_thresholds") or [float(ckpt.get("inference_threshold_default", 0.5))] * max(1, len(target_cols))),
            dtype=np.float64,
        )
        if target_cols and thresholds.shape[0] != len(target_cols):
            thresholds = np.asarray([float(ckpt.get("inference_threshold_default", 0.5))] * len(target_cols), dtype=np.float64)
        z_np = z_latent.detach().cpu().numpy().astype(np.float32, copy=False)

        if task_mode == "multiclass":
            probs = torch.softmax(logits, dim=1).detach().cpu().numpy().astype(np.float32, copy=False)
            pred_idx = np.argmax(probs, axis=1).astype(np.int64, copy=False)
            for idx in range(n_windows):
                label = class_names[int(pred_idx[idx])] if class_names and int(pred_idx[idx]) < len(class_names) else str(int(pred_idx[idx]))
                rows.append(
                    {
                        **chunk_meta[idx],
                        "pred_index": int(pred_idx[idx]),
                        "pred_label": str(label),
                        "pred_confidence": float(np.max(probs[idx])),
                        "probabilities": {
                            class_names[j] if j < len(class_names) else f"class_{j}": float(probs[idx, j])
                            for j in range(probs.shape[1])
                        },
                        "latent_norm": float(np.linalg.norm(z_np[idx])),
                    }
                )
        elif task_mode == "multilabel":
            probs = torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32, copy=False)
            preds = (probs >= thresholds.reshape(1, -1)).astype(np.int64, copy=False)
            for idx in range(n_windows):
                states: List[Dict[str, Any]] = []
                confs: List[float] = []
                bits: List[str] = []
                labels: List[str] = []
                for j, name in enumerate(target_cols):
                    p_on = float(probs[idx, j])
                    conf = float(max(p_on, 1.0 - p_on))
                    pred_on = int(preds[idx, j]) == 1
                    confs.append(conf)
                    bits.append(str(int(pred_on)))
                    labels.append(f"{name}={'on' if pred_on else 'off'}")
                    states.append(
                        {
                            "name": str(name),
                            "probability_on": p_on,
                            "threshold": float(thresholds[j]),
                            "predicted": int(pred_on),
                            "predicted_state": ("on" if pred_on else "off"),
                            "confidence": conf,
                        }
                    )
                rows.append(
                    {
                        **chunk_meta[idx],
                        "pred_bits": "|".join(bits),
                        "pred_label": "|".join(labels),
                        "pred_confidence_mean": float(np.mean(confs)) if confs else None,
                        "pred_confidence_min": float(np.min(confs)) if confs else None,
                        "pred_confidence_combo": float(np.prod(np.asarray(confs, dtype=np.float64))) if confs else None,
                        "states": states,
                        "latent_norm": float(np.linalg.norm(z_np[idx])),
                    }
                )
        else:
            pred = logits.detach().cpu().numpy().astype(np.float32, copy=False)
            reg_mean = np.asarray(ckpt.get("regression_target_mean") or [], dtype=np.float32)
            reg_std = np.asarray(ckpt.get("regression_target_std") or [], dtype=np.float32)
            if reg_mean.size and reg_std.size and reg_mean.shape[0] == pred.shape[1] and reg_std.shape[0] == pred.shape[1]:
                pred = (pred * reg_std.reshape(1, -1)) + reg_mean.reshape(1, -1)
            for idx in range(n_windows):
                out_vals = {
                    str(target_cols[j] if j < len(target_cols) else f"target_{j}"): float(pred[idx, j])
                    for j in range(pred.shape[1])
                }
                rows.append(
                    {
                        **chunk_meta[idx],
                        "pred_label": json.dumps(out_vals, sort_keys=True),
                        "regression": out_vals,
                        "latent_norm": float(np.linalg.norm(z_np[idx])),
                    }
                )

        return {
            "normalized_audio": self._audio_file_stats(wav_path),
            "task_mode": task_mode,
            "embedding_dim": int(emb.shape[1]),
            "latent_dim": int(z_np.shape[1]) if z_np.ndim == 2 else 0,
            "n_windows": int(len(rows)),
            "windows": rows,
        }

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

    def query_parquet(
        self,
        *,
        path: str,
        rows: int = 25,
        filter_col: str = "",
        filter_val: str = "",
        pca1: str = "",
        pca2: str = "",
        pca3: str = "",
        display_cols: str = "",
    ) -> Dict[str, Any]:
        p = self._check_allowed(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if p.suffix.lower() != ".parquet":
            raise ValueError("query_parquet requires a parquet file")
        df = pd.read_parquet(p)
        if df.empty:
            return {"path": str(p), "total_rows": 0, "display_cols": [], "rows": []}

        out = df.copy()
        fc = str(filter_col).strip()
        fv = str(filter_val).strip()
        if fc and fv:
            if fc not in out.columns:
                raise ValueError(f"filter column not found: {fc}")
            out = out[out[fc].astype("string").str.contains(fv, case=False, regex=False, na=False)].copy()

        use_nearest = all(str(x).strip() for x in (pca1, pca2, pca3))
        if use_nearest:
            req = ["pca1", "pca2", "pca3"]
            missing = [c for c in req if c not in out.columns]
            if missing:
                raise ValueError(f"missing PCA columns: {', '.join(missing)}")
            out["dist2"] = (
                (pd.to_numeric(out["pca1"], errors="coerce") - float(pca1)) ** 2
                + (pd.to_numeric(out["pca2"], errors="coerce") - float(pca2)) ** 2
                + (pd.to_numeric(out["pca3"], errors="coerce") - float(pca3)) ** 2
            )
            out = out[out["dist2"].notna()].sort_values("dist2", ascending=True)

        total = int(len(out))
        dcols = [c.strip() for c in str(display_cols).split(",") if c.strip()]
        if not dcols:
            preferred = [
                "sample_id",
                "segment_path",
                "audio_source",
                "split",
                "actuation_trit",
                "actuation_combo",
                "pca1",
                "pca2",
                "pca3",
                "dist2",
            ]
            dcols = [c for c in preferred if c in out.columns]
        keep_extra = [c for c in ("segment_path", "mel_shard_path", "mel_shard_local_index") if c in out.columns and c not in dcols]
        cols = [c for c in dcols if c in out.columns] + keep_extra
        out = out.head(max(1, min(int(rows), 500))).copy()
        for c in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[c]):
                out[c] = out[c].astype("string")
        return {
            "path": str(p),
            "total_rows": total,
            "display_cols": [c for c in dcols if c in out.columns],
            "rows": out[cols].to_dict(orient="records"),
        }


def _q1(params: Dict[str, List[str]], key: str, default: str = "") -> str:
    vals = params.get(key)
    if not vals:
        return default
    return str(vals[0])


def _safe_under_root(root: Path, rel_path: str) -> Path:
    target = (root / rel_path.lstrip("/")).resolve()
    target.relative_to(root)
    return target


def _render_root_index_html(*, root_aliases: Dict[str, Path]) -> str:
    rows: List[str] = []
    for alias, root in sorted(root_aliases.items(), key=lambda kv: kv[0].lower()):
        rows.append(
            f"<tr><td><a href=\"/raw/{quote(alias)}/\">{alias}</a></td><td>{root}</td><td>dir</td></tr>"
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8' />"
        "<title>Raw Browser</title>"
        "<style>body{font-family:sans-serif;margin:12px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ddd;padding:6px;font-size:12px;text-align:left}"
        "th{background:#f3f3f3}</style></head><body>"
        "<h3>Index of /raw/</h3>"
        "<div>Available roots</div>"
        "<table><thead><tr><th>alias</th><th>path</th><th>type</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )


def _render_dir_listing_html(*, root_alias: str, root: Path, req_rel: str, target: Path) -> str:
    title = f"Index of /raw/{root_alias}/{req_rel.lstrip('/')}".rstrip("/")
    rows: List[str] = []
    rows.append(
        "<tr><td><a href=\"/raw/\">..</a></td><td>dir</td><td></td></tr>"
    )
    if req_rel.strip("/"):
        parent_rel = str(Path(req_rel).parent)
        if parent_rel == ".":
            parent_rel = ""
        rows.append(
            f"<tr><td><a href=\"/raw/{quote(root_alias)}/{quote(parent_rel)}\">parent</a></td><td>dir</td><td></td></tr>"
        )
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        child_rel = str((Path(req_rel) / child.name).as_posix()).lstrip("./")
        href = f"/raw/{quote(root_alias)}/{quote(child_rel)}"
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
        f"<div>root: {root_alias} -> {root}</div>"
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


def _plot_waveform_and_spectrogram_png(y: np.ndarray, *, sample_rate: int, title: str) -> bytes:
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = np.asarray(y, dtype=np.float32)
    t = np.arange(y.shape[0], dtype=np.float64) / max(float(sample_rate), 1.0)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    axes[0].plot(t, y, linewidth=0.8, color="#005f73")
    axes[0].set_title(f"Waveform: {title}")
    axes[0].set_xlabel("time (s)")
    axes[0].set_ylabel("amplitude")
    axes[0].grid(alpha=0.2)
    axes[1].specgram(y, NFFT=1024, Fs=float(sample_rate), noverlap=512, cmap="magma")
    axes[1].set_title("Spectrogram")
    axes[1].set_xlabel("time (s)")
    axes[1].set_ylabel("freq (Hz)")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()


def _load_wav_for_spec(path: Path) -> tuple[np.ndarray, int]:
    if sf is not None:
        data, sr = sf.read(str(path), always_2d=False)
        y = np.asarray(data, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y, int(sr)
    if wavfile is not None:
        sr, data = wavfile.read(str(path))
        y = np.asarray(data, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y, int(sr)
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if sampwidth != 2:
        raise ValueError(f"unsupported wav sample width without soundfile/scipy: {sampwidth} bytes")
    y = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if n_channels > 1:
        y = y.reshape(-1, n_channels).mean(axis=1)
    return y, int(rate)


def _sanitize_upload_name(name: str) -> str:
    base = Path(str(name or "upload.bin")).name
    safe = "".join(ch if (ch.isalnum() or ch in {".", "_", "-"}) else "_" for ch in base)
    safe = safe.strip("._") or "upload.bin"
    return safe[:128]


def _convert_to_wav_ffmpeg(
    *,
    src: Path,
    dst: Path,
    sample_rate: int,
    channels: int,
    pcm_codec: str,
) -> None:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        str(int(channels)),
        "-ar",
        str(int(sample_rate)),
        "-acodec",
        str(pcm_codec),
        str(dst),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg.")
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "").strip() or f"ffmpeg exit={res.returncode}")


def _write_wav_pcm16(path: Path, y: np.ndarray, *, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(y, dtype=np.float32)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = np.asarray(np.round(arr * 32767.0), dtype=np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())


def _summarize_classic_prediction(pred: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(pred)
    if "prediction_label" in out and "pred_label" not in out:
        out["pred_label"] = out.get("prediction_label")
    if "predicted_label" in out and "pred_label" not in out:
        out["pred_label"] = out.get("predicted_label")
    if "predicted_class" in out and "pred_label" not in out:
        out["pred_label"] = out.get("predicted_class")
    if "predicted_index" in out and "pred_index" not in out:
        out["pred_index"] = out.get("predicted_index")
    probs = out.get("probabilities")
    if isinstance(probs, dict) and probs:
        out["pred_confidence"] = float(max(float(v) for v in probs.values()))
    elif "pred_confidence" not in out:
        for key in ("confidence", "probability", "score"):
            if key in out:
                out["pred_confidence"] = out[key]
                break
    return out


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
                if path == "/parquet":
                    self._write_html(PARQUET_QUERY_HTML)
                    return
                if path == "/upload":
                    self._write_html(UPLOAD_HTML)
                    return
                if path.startswith("/raw"):
                    raw_rel = unquote(path[len("/raw") :]).lstrip("/")
                    if not raw_rel:
                        self._write_html(_render_root_index_html(root_aliases=state.allowed_root_aliases))
                        return
                    parts = Path(raw_rel).parts
                    root_alias = str(parts[0])
                    root = state.allowed_root_aliases.get(root_alias)
                    if root is None:
                        self._write_json({"error": f"unknown raw root alias: {root_alias}"}, code=404)
                        return
                    req_rel = str(Path(*parts[1:]).as_posix()) if len(parts) > 1 else ""
                    target = _safe_under_root(root, req_rel)
                    if not target.exists():
                        self._write_json({"error": f"not found: {target}"}, code=404)
                        return
                    if target.is_dir():
                        self._write_html(
                            _render_dir_listing_html(
                                root_alias=root_alias,
                                root=root,
                                req_rel=req_rel,
                                target=target,
                            )
                        )
                        return
                    mime, _enc = mimetypes.guess_type(str(target))
                    self._write_bytes(target.read_bytes(), content_type=(mime or "application/octet-stream"))
                    return
                if path == "/api/summary":
                    self._write_json(state.summary())
                    return
                if path == "/api/windows":
                    out = state.windows(
                        site=_q1(q, "site", ""),
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
                if path == "/api/models":
                    self._write_json(state.list_models(limit=int(_q1(q, "limit", "1000"))))
                    return
                if path == "/api/files":
                    p = _q1(q, "path", str(state.samples_paths[0].parent))
                    self._write_json(state.list_dir(p))
                    return
                if path == "/api/file":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    self._write_json(state.preview_file(p, rows=int(_q1(q, "rows", "20"))))
                    return
                if path == "/api/parquet_query":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    self._write_json(
                        state.query_parquet(
                            path=p,
                            rows=int(_q1(q, "rows", "25")),
                            filter_col=_q1(q, "filter_col", ""),
                            filter_val=_q1(q, "filter_val", ""),
                            pca1=_q1(q, "pca1", ""),
                            pca2=_q1(q, "pca2", ""),
                            pca3=_q1(q, "pca3", ""),
                            display_cols=_q1(q, "display_cols", ""),
                        )
                    )
                    return
                if path == "/audio":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    self._write_bytes(state.read_audio_bytes(p), content_type="audio/wav", code=200)
                    return
                if path == "/image":
                    p = _q1(q, "path", "")
                    if not p:
                        self._write_json({"error": "path is required"}, code=400)
                        return
                    img_p = state._check_allowed(p)
                    if not img_p.exists():
                        self._write_json({"error": f"not found: {img_p}"}, code=404)
                        return
                    mime, _enc = mimetypes.guess_type(str(img_p))
                    self._write_bytes(img_p.read_bytes(), content_type=(mime or "application/octet-stream"), code=200)
                    return
                if path == "/spectrogram":
                    png = state.render_spectrogram_png(
                        path=_q1(q, "path", ""),
                        mel_shard_path=_q1(q, "mel_shard_path", ""),
                        mel_index=int(_q1(q, "mel_index", "0")),
                    )
                    self._write_bytes(png, content_type="image/png", code=200)
                    return
                if path == "/api/infer":
                    wav = _q1(q, "path", "")
                    model = _q1(q, "model", "")
                    if not wav or not model:
                        self._write_json({"error": "path and model are required"}, code=400)
                        return
                    out = state.infer_audio(
                        path=wav,
                        model=model,
                        model_kind=_q1(q, "model_kind", "auto"),
                    )
                    self._write_json(out)
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

        def do_POST(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path != "/api/upload_infer":
                    self._write_json({"error": f"not found: {parsed.path}"}, code=404)
                    return
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    },
                )
                file_item = form["audio"] if "audio" in form else None
                if file_item is None or not getattr(file_item, "file", None):
                    self._write_json({"error": "audio file is required"}, code=400)
                    return
                upload_name = str(getattr(file_item, "filename", "") or "upload.bin")
                upload_bytes = file_item.file.read()
                if not upload_bytes:
                    self._write_json({"error": "uploaded file is empty"}, code=400)
                    return
                model = str(form.getfirst("model", "") or "").strip()
                if not model:
                    self._write_json({"error": "model is required"}, code=400)
                    return
                model_kind = str(form.getfirst("model_kind", "auto") or "auto")
                window_seconds = float(str(form.getfirst("window_seconds", "10") or "10"))
                out = state.infer_uploaded_audio(
                    upload_name=upload_name,
                    upload_bytes=upload_bytes,
                    model=model,
                    model_kind=model_kind,
                    window_seconds=window_seconds,
                )
                self._write_json(out)
            except FileNotFoundError as exc:
                self._write_json({"error": str(exc)}, code=404)
            except PermissionError as exc:
                self._write_json({"error": str(exc)}, code=403)
            except Exception as exc:
                self._write_json({"error": str(exc)}, code=500)

    return Handler


def main() -> int:
    args = _arg_parser().parse_args()
    sample_paths: List[Path] = []
    for p in (args.samples_parquet or []):
        if str(p).strip():
            sample_paths.append(Path(str(p)).expanduser().resolve())
    if args.samples_glob:
        for p in sorted(glob.glob(str(args.samples_glob), recursive=True)):
            sample_paths.append(Path(p).expanduser().resolve())
    if not sample_paths:
        sample_paths = [Path(DEFAULT_SAMPLES).expanduser().resolve()]
    # Deduplicate while preserving order.
    dedup: List[Path] = []
    seen = set()
    for p in sample_paths:
        rp = p.resolve()
        if str(rp) not in seen:
            seen.add(str(rp))
            dedup.append(rp)
    sample_paths = dedup
    missing = [p for p in sample_paths if not p.exists()]
    if missing:
        raise SystemExit("samples parquet not found:\n" + "\n".join(str(p) for p in missing))
    roots = [Path(p).expanduser().resolve() for p in args.allow_root]
    if not roots:
        roots = _default_allowed_roots(sample_paths)
    models_dir = Path(args.models_dir).expanduser().resolve()
    state = AppState(sample_paths, roots, models_dir=models_dir, upload_root=DEFAULT_UPLOAD_ROOT)
    handler = make_handler(state)
    server = ThreadingHTTPServer((str(args.host), int(args.port)), handler)
    print(f"[ok] serving http://{args.host}:{args.port}", flush=True)
    print(f"[ok] samples={len(sample_paths)}", flush=True)
    for sp in sample_paths:
        print(f"      - {sp}", flush=True)
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
