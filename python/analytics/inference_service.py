#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd

def _ensure_repo_on_syspath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_on_syspath()

from worker_main import run_audio_inference_job


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_ts(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _coerce_points(points: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for p in points:
        ts = _parse_ts(p.get("ts") if "ts" in p else p.get("timestamp"))
        if ts is None:
            continue
        val = p.get("value")
        try:
            valf = float(val) if val is not None else float("nan")
        except Exception:
            valf = float("nan")
        rows.append({"ts": float(ts), "value": float(valf)})
    if not rows:
        raise ValueError("no valid points with timestamp")
    df = pd.DataFrame(rows).sort_values("ts").drop_duplicates(subset=["ts"], keep="last").reset_index(drop=True)
    return df


def _reconstruct_naive_linear(points: List[Dict[str, Any]], *, max_gap_seconds: float) -> Dict[str, Any]:
    df = _coerce_points(points)
    is_missing = df["value"].isna()
    if not bool(is_missing.any()):
        return {
            "method": "naive_linear",
            "n_points": int(len(df)),
            "n_reconstructed": 0,
            "points": df.assign(reconstructed=False).to_dict(orient="records"),
        }

    out = df.copy()
    out["reconstructed"] = False
    idx_missing = out.index[out["value"].isna()].tolist()
    for i in idx_missing:
        j0 = i - 1
        while j0 >= 0 and pd.isna(out.at[j0, "value"]):
            j0 -= 1
        j1 = i + 1
        while j1 < len(out) and pd.isna(out.at[j1, "value"]):
            j1 += 1
        if j0 < 0 or j1 >= len(out):
            continue
        t0, v0 = float(out.at[j0, "ts"]), float(out.at[j0, "value"])
        t1, v1 = float(out.at[j1, "ts"]), float(out.at[j1, "value"])
        dt = float(t1 - t0)
        if dt <= 0 or dt > float(max_gap_seconds):
            continue
        ti = float(out.at[i, "ts"])
        alpha = (ti - t0) / dt
        out.at[i, "value"] = (1.0 - alpha) * v0 + alpha * v1
        out.at[i, "reconstructed"] = True

    return {
        "method": "naive_linear",
        "n_points": int(len(out)),
        "n_reconstructed": int(out["reconstructed"].sum()),
        "points": out.to_dict(orient="records"),
    }


def _write_json(handler: BaseHTTPRequestHandler, payload: Dict[str, Any], code: int = 200) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    n = int(handler.headers.get("Content-Length", "0") or "0")
    if n <= 0:
        return {}
    b = handler.rfile.read(n)
    if not b:
        return {}
    return json.loads(b.decode("utf-8"))


def make_handler(*, artifacts_root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "svwatergo-inference/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                _write_json(
                    self,
                    {
                        "status": "ok",
                        "service": "inference_service",
                        "time": _iso_now(),
                        "artifacts_root": str(artifacts_root),
                    },
                    code=200,
                )
                return
            _write_json(self, {"error": "not_found"}, code=404)

        def do_POST(self) -> None:  # noqa: N802
            try:
                req = _read_json(self)
            except Exception as e:
                _write_json(self, {"error": f"invalid_json: {e}"}, code=400)
                return

            try:
                if self.path == "/api/v1/inference/audio":
                    rid = f"infer-{int(time.time())}-{uuid4().hex[:8]}"
                    out_dir = artifacts_root / rid
                    out_dir.mkdir(parents=True, exist_ok=True)
                    payload, arts = run_audio_inference_job(req, out_dir)
                    _write_json(
                        self,
                        {
                            "status": "succeeded",
                            "request_id": rid,
                            "artifacts_dir": str(out_dir),
                            "payload": payload,
                            "artifacts": arts,
                        },
                        code=200,
                    )
                    return

                if self.path == "/api/v1/inference/gap-reconstruct":
                    method = str(req.get("method", "naive_linear")).strip().lower()
                    points = list(req.get("points") or [])
                    max_gap_s = float(req.get("max_gap_seconds") or 300.0)
                    if method == "naive_linear":
                        out = _reconstruct_naive_linear(points, max_gap_seconds=max_gap_s)
                    elif method in ("kalman", "digital_twin"):
                        out = {
                            "method": method,
                            "status": "not_implemented_yet",
                            "message": "method planned; use naive_linear for now",
                        }
                    else:
                        raise ValueError(f"unsupported method: {method}")
                    _write_json(self, {"status": "succeeded", "payload": out}, code=200)
                    return

                _write_json(self, {"error": "not_found"}, code=404)
            except ValueError as e:
                _write_json(self, {"error": f"bad_request: {e}"}, code=400)
            except Exception as e:
                _write_json(self, {"error": f"internal_error: {e}"}, code=500)

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="SVWaterGo long-running inference service")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--artifacts-root", default="data/analytics/inference_service")
    args = ap.parse_args()

    artifacts_root = Path(args.artifacts_root).expanduser().resolve()
    artifacts_root.mkdir(parents=True, exist_ok=True)
    handler = make_handler(artifacts_root=artifacts_root)
    server = ThreadingHTTPServer((str(args.host), int(args.port)), handler)
    print(f"[inference_service] listening on http://{args.host}:{args.port}", flush=True)
    print(f"[inference_service] artifacts_root={artifacts_root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
