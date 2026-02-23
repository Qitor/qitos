"""qita CLI: web board, trace viewer, replay, and export."""

from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="qita", description="QitOS trace tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_board = sub.add_parser("board", help="Start qita web board")
    p_board.add_argument("--logdir", default="./runs", help="Trace runs root directory")
    p_board.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_board.add_argument("--port", type=int, default=8765, help="Bind port")

    p_replay = sub.add_parser("replay", help="Open one run in web replay mode")
    p_replay.add_argument("--run", required=True, help="Run directory path")
    p_replay.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_replay.add_argument("--port", type=int, default=8765, help="Bind port")

    p_export = sub.add_parser("export", help="Export one run to standalone HTML")
    p_export.add_argument("--run", required=True, help="Run directory path")
    p_export.add_argument("--html", required=True, help="Output html file path")

    args = parser.parse_args(argv)
    if args.command == "board":
        return _cmd_board(logdir=args.logdir, host=args.host, port=args.port, focus_run_id=None, replay=False)
    if args.command == "replay":
        return _cmd_replay(run=args.run, host=args.host, port=args.port)
    if args.command == "export":
        return _cmd_export(run=args.run, html_path=args.html)
    return 1


def _cmd_board(logdir: str, host: str, port: int, focus_run_id: Optional[str], replay: bool) -> int:
    root = Path(logdir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    handler_cls = _build_handler(root=root)
    server = ThreadingHTTPServer((host, port), handler_cls)
    path = "/"
    if focus_run_id:
        safe_id = _slug_run_id(focus_run_id)
        path = f"/replay/{safe_id}" if replay else f"/run/{safe_id}"
    print(f"[qita] board logdir: {root}")
    print(f"[qita] runs discovered: {len(_discover_runs(root))}")
    print(f"[qita] open: http://{host}:{port}{path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[qita] board stopped")
    return 0


def _cmd_replay(run: str, host: str, port: int) -> int:
    run_dir = Path(run).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")
    root = run_dir.parent
    run_id = run_dir.name
    return _cmd_board(logdir=str(root), host=host, port=port, focus_run_id=run_id, replay=True)


def _cmd_export(run: str, html_path: str) -> int:
    run_dir = Path(run).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")
    payload = _load_run_payload(run_dir)
    out = Path(html_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_run_html(payload, embedded=True), encoding="utf-8")
    print(f"[qita] exported: {out}")
    return 0


def _build_handler(root: Path):
    class QitaHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            route = parsed.path
            qs = parse_qs(parsed.query)
            if route == "/":
                self._send_html(_render_board_html())
                return
            if route == "/api/runs":
                self._send_json(_discover_runs(root))
                return
            if route.startswith("/api/run/"):
                run_id = _slug_run_id(route.split("/", 3)[-1])
                run_dir = _resolve_run(root, run_id)
                if run_dir is None:
                    self._send_json({"error": "run not found", "run_id": run_id}, status=404)
                    return
                self._send_json(_load_run_payload(run_dir))
                return
            if route.startswith("/run/"):
                run_id = _slug_run_id(route.split("/", 2)[-1])
                run_dir = _resolve_run(root, run_id)
                if run_dir is None:
                    self._send_html(_render_not_found(run_id), status=404)
                    return
                self._send_html(_render_run_html(_load_run_payload(run_dir), embedded=False))
                return
            if route.startswith("/replay/"):
                run_id = _slug_run_id(route.split("/", 2)[-1])
                run_dir = _resolve_run(root, run_id)
                if run_dir is None:
                    self._send_html(_render_not_found(run_id), status=404)
                    return
                speed = int((qs.get("speed") or ["500"])[0])
                self._send_html(_render_replay_html(_load_run_payload(run_dir), speed_ms=max(100, speed)))
                return
            if route.startswith("/export/raw/"):
                run_id = _slug_run_id(route.split("/", 3)[-1])
                run_dir = _resolve_run(root, run_id)
                if run_dir is None:
                    self._send_json({"error": "run not found", "run_id": run_id}, status=404)
                    return
                payload = _load_run_payload(run_dir)
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self._send_bytes(
                    body,
                    content_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
                )
                return
            if route.startswith("/export/html/"):
                run_id = _slug_run_id(route.split("/", 3)[-1])
                run_dir = _resolve_run(root, run_id)
                if run_dir is None:
                    self._send_json({"error": "run not found", "run_id": run_id}, status=404)
                    return
                payload = _load_run_payload(run_dir)
                body = _render_run_html(payload, embedded=True).encode("utf-8")
                self._send_bytes(
                    body,
                    content_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}.html"'},
                )
                return
            self._send_json({"error": "not found", "route": route}, status=404)

        def log_message(self, fmt: str, *args: Any) -> None:
            # Keep console clean; qita already prints startup summary.
            _ = fmt
            _ = args

        def _send_html(self, body: str, status: int = 200) -> None:
            self._send_bytes(body.encode("utf-8"), content_type="text/html; charset=utf-8", status=status)

        def _send_json(self, obj: Any, status: int = 200) -> None:
            self._send_bytes(
                json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
                status=status,
            )

        def _send_bytes(
            self,
            body: bytes,
            content_type: str,
            status: int = 200,
            headers: Optional[Dict[str, str]] = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

    return QitaHandler


def _resolve_run(root: Path, run_id: str) -> Optional[Path]:
    run_dir = (root / run_id).resolve()
    if run_dir.exists() and run_dir.is_dir() and run_dir.parent == root:
        return run_dir
    return None


def _slug_run_id(run_id: str) -> str:
    return "".join(c for c in run_id if c.isalnum() or c in ("-", "_", "."))


def _discover_runs(logdir: Path) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    if not logdir.exists():
        return runs
    for p in sorted(logdir.iterdir()):
        if not p.is_dir():
            continue
        manifest_path = p / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = _load_json(manifest_path)
        summary = manifest.get("summary") or {}
        runs.append(
            {
                "id": p.name,
                "path": str(p),
                "status": manifest.get("status"),
                "updated_at": manifest.get("updated_at"),
                "step_count": manifest.get("step_count", 0),
                "event_count": manifest.get("event_count", 0),
                "stop_reason": summary.get("stop_reason"),
                "final_result": summary.get("final_result"),
                "manifest_meta": {
                    "schema_version": manifest.get("schema_version"),
                    "model_id": manifest.get("model_id"),
                    "prompt_hash": manifest.get("prompt_hash"),
                    "run_config_hash": manifest.get("run_config_hash"),
                    "seed": manifest.get("seed"),
                    "summary_steps": summary.get("steps"),
                },
            }
        )
    return runs


def _load_run_payload(run_dir: Path) -> Dict[str, Any]:
    manifest = _load_json(run_dir / "manifest.json")
    events = _load_jsonl(run_dir / "events.jsonl")
    steps = _load_jsonl(run_dir / "steps.jsonl")
    grouped_events = _group_events_by_step(events)
    return {
        "run": str(run_dir),
        "run_id": run_dir.name,
        "manifest": manifest,
        "events": events,
        "steps": steps,
        "events_by_step": grouped_events,
    }


def _group_events_by_step(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        sid = str(ev.get("step_id", "none"))
        grouped.setdefault(sid, []).append(ev)
    return grouped


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"raw": line, "error": "invalid_json"})
    return out


def _render_board_html() -> str:
    return """<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>qita board</title>
<style>
:root{--bg:#090d16;--panel:#10192a;--panel2:#0d1422;--line:#1f2f4d;--txt:#e7edf9;--muted:#9fb0d4;--ok:#3dd68c;--warn:#f7b955;--bad:#ff6b6b;--accent:#4db5ff}
*{box-sizing:border-box} body{margin:0;font-family:ui-sans-serif,system-ui;background:radial-gradient(circle at 20% 0%,#132340 0,#090d16 60%);color:var(--txt)}
.wrap{max-width:1320px;margin:0 auto;padding:24px 18px 32px}
.head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.title{font-size:28px;font-weight:800;letter-spacing:.2px}.sub{color:var(--muted);font-size:13px;margin-top:4px}
.chip{border:1px solid var(--line);background:var(--panel2);border-radius:999px;padding:8px 12px;font-size:12px;color:var(--muted)}
.toolbar{display:grid;grid-template-columns:1.5fr 1fr 1fr auto auto;gap:10px;margin:12px 0 18px}
.toolbar input,.toolbar select{border:1px solid var(--line);background:var(--panel2);color:var(--txt);border-radius:10px;padding:9px 10px;font-size:13px}
.toolbar label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.toolbar .btn{justify-content:center}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,.00));border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 10px 30px rgba(0,0,0,.15)}
.id{font-weight:700;font-size:16px}
.meta{font-size:12px;color:var(--muted);margin-top:6px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{display:inline-flex;align-items:center;border:1px solid var(--line);color:var(--txt);background:#13203a;padding:6px 10px;border-radius:8px;font-size:12px;text-decoration:none;cursor:pointer}
.btn:hover{border-color:var(--accent)}
.state{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;background:#13342b;color:var(--ok);border:1px solid #1d5f4b}
.manifest-mini{margin-top:8px;border:1px dashed #27416a;border-radius:10px;padding:8px;background:#0d182c}
.manifest-mini .meta{margin-top:2px}
.manifest-meta-tree{margin-top:6px;padding-top:6px;border-top:1px dashed #27416a}
.manifest-meta-tree details{margin:4px 0}
.manifest-meta-tree summary{cursor:pointer;color:#b7cdf4;font-size:12px}
.manifest-meta-leaf{display:grid;grid-template-columns:110px 1fr;gap:8px;margin:4px 0}
.manifest-meta-k{font-size:11px;color:#8ea4cf}
.manifest-meta-v{font-size:11px;color:#dce8ff;word-break:break-word}
.empty{padding:18px;border:1px dashed var(--line);border-radius:12px;color:var(--muted)}
@media (max-width:980px){.toolbar{grid-template-columns:1fr 1fr}}
</style></head>
<body>
<div class="wrap">
  <div class="head">
    <div>
      <div class="title">QitOS · qita board</div>
      <div class="sub">Runs, trace inspection, replay, and export</div>
    </div>
    <div class="chip" id="summary">Loading...</div>
  </div>
  <div class="toolbar">
    <input id="q" placeholder="Search run id / stop reason / final result"/>
    <select id="status"><option value="">All status</option></select>
    <select id="sort">
      <option value="updated_desc">Sort: updated desc</option>
      <option value="updated_asc">Sort: updated asc</option>
      <option value="events_desc">Sort: events desc</option>
      <option value="steps_desc">Sort: steps desc</option>
    </select>
    <label><input type="checkbox" id="auto" checked/>Auto refresh</label>
    <button class="btn" id="refresh">Refresh</button>
  </div>
  <div id="stats" class="grid" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr));margin-bottom:12px"></div>
  <div id="runs" class="grid"></div>
</div>
<script>
let allRuns = [];
function parseTime(s){
  if(!s){ return 0; }
  const v = Date.parse(s);
  return Number.isNaN(v) ? 0 : v;
}
function esc(s){
  return String(s).replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; });
}
function preview(v){
  if(v === null || v === undefined) return '-';
  if(typeof v === 'string') return v.length > 120 ? (v.slice(0, 120) + '...') : v;
  if(typeof v === 'number' || typeof v === 'boolean') return String(v);
  if(Array.isArray(v)) return '[' + v.length + ' items]';
  if(typeof v === 'object') return '{...}';
  return String(v);
}
function metaLeaf(k, v){
  return '<div class="manifest-meta-leaf"><div class="manifest-meta-k">'+esc(k)+'</div><div class="manifest-meta-v">'+esc(preview(v))+'</div></div>';
}
function metaTree(k, v, depth){
  if(v === null || v === undefined) return metaLeaf(k, v);
  if(Array.isArray(v)){
    const lim = Math.min(v.length, 50);
    let inner = '';
    for(let i=0;i<lim;i+=1) inner += metaTree('['+i+']', v[i], depth + 1);
    if(v.length > lim) inner += metaLeaf('...', '+' + (v.length - lim) + ' more items');
    const open = depth < 1 ? ' open' : '';
    return '<details'+open+'><summary>'+esc(k)+' <span class="meta">array('+v.length+')</span></summary>' + inner + '</details>';
  }
  if(typeof v === 'object'){
    const keys = Object.keys(v);
    const lim = Math.min(keys.length, 50);
    let inner = '';
    for(let i=0;i<lim;i+=1){ const kk = keys[i]; inner += metaTree(kk, v[kk], depth + 1); }
    if(keys.length > lim) inner += metaLeaf('...', '+' + (keys.length - lim) + ' more keys');
    const open = depth < 1 ? ' open' : '';
    return '<details'+open+'><summary>'+esc(k)+' <span class="meta">object('+keys.length+')</span></summary>' + inner + '</details>';
  }
  return metaLeaf(k, v);
}
function paint(){
  const q = (document.getElementById('q').value || '').toLowerCase();
  const status = document.getElementById('status').value;
  const sort = document.getElementById('sort').value;
  let runs = allRuns.filter((r)=>{
    const blob = `${r.id||''} ${r.stop_reason||''} ${r.final_result||''}`.toLowerCase();
    if(q && !blob.includes(q)){ return false; }
    if(status && (r.status||'') !== status){ return false; }
    return true;
  });
  runs = runs.slice();
  if(sort === 'updated_desc'){ runs.sort((a,b)=>parseTime(b.updated_at)-parseTime(a.updated_at)); }
  else if(sort === 'updated_asc'){ runs.sort((a,b)=>parseTime(a.updated_at)-parseTime(b.updated_at)); }
  else if(sort === 'events_desc'){ runs.sort((a,b)=>(b.event_count||0)-(a.event_count||0)); }
  else if(sort === 'steps_desc'){ runs.sort((a,b)=>(b.step_count||0)-(a.step_count||0)); }
  const root = document.getElementById('runs');
  const statsRoot = document.getElementById('stats');
  document.getElementById('summary').textContent = `${runs.length} shown / ${allRuns.length} total`;
  const stats = calcStats(allRuns);
  statsRoot.innerHTML = `
    <div class="card"><div class="meta">Success Rate</div><div class="id">${stats.successRate}</div><div class="meta">${stats.successCount}/${stats.total} runs</div></div>
    <div class="card"><div class="meta">Avg Steps</div><div class="id">${stats.avgSteps}</div><div class="meta">per run</div></div>
    <div class="card"><div class="meta">Avg Events</div><div class="id">${stats.avgEvents}</div><div class="meta">per run</div></div>
    <div class="card"><div class="meta">Failure Top-3</div><div class="meta">${stats.failureTop}</div></div>
  `;
  if(!runs.length){ root.innerHTML = `<div class="empty">No runs found in current logdir.</div>`; return; }
  root.innerHTML = '';
  for(const r of runs){
    const el = document.createElement('div');
    el.className = 'card';
    const status = (r.status || 'unknown');
    const m = r.manifest_meta || {};
    el.innerHTML = `
      <div class="id">${r.id}</div>
      <div class="meta"><span class="state">${status}</span> steps=${r.step_count||0} events=${r.event_count||0}</div>
      <div class="meta">stop=${r.stop_reason||''}</div>
      <div class="meta">updated=${r.updated_at||''}</div>
      <div class="manifest-mini">
        <div class="meta">manifest meta</div>
        <div class="meta">model=${m.model_id||''}</div>
        <div class="meta">schema=${m.schema_version||''} seed=${m.seed===null?'null':(m.seed||'')}</div>
        <div class="meta">prompt_hash=${m.prompt_hash||''}</div>
        <details class="manifest-meta-tree">
          <summary>Full manifest meta</summary>
          ${metaTree('manifest_meta', m, 0)}
        </details>
      </div>
      <div class="row">
        <a class="btn" href="/run/${encodeURIComponent(r.id)}">view</a>
        <a class="btn" href="/replay/${encodeURIComponent(r.id)}">replay</a>
        <a class="btn" href="/export/raw/${encodeURIComponent(r.id)}">export raw</a>
        <a class="btn" href="/export/html/${encodeURIComponent(r.id)}">export html</a>
      </div>`;
    root.appendChild(el);
  }
}
function calcStats(runs){
  const total = runs.length;
  let successCount = 0;
  let stepSum = 0;
  let eventSum = 0;
  const fail = new Map();
  for(const r of runs){
    const status = String(r.status||'').toLowerCase();
    const stop = String(r.stop_reason||'').toLowerCase();
    const ok = (status === 'completed' || status === 'success') && !stop.includes('error') && !stop.includes('fail');
    if(ok) successCount += 1;
    stepSum += Number(r.step_count||0);
    eventSum += Number(r.event_count||0);
    if(!ok){
      const k = stop || status || 'unknown_failure';
      fail.set(k, (fail.get(k)||0) + 1);
    }
  }
  const top = Array.from(fail.entries()).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>`${k}:${v}`).join(' | ') || 'none';
  return {
    total,
    successCount,
    successRate: total ? `${((successCount/total)*100).toFixed(1)}%` : '0%',
    avgSteps: total ? (stepSum/total).toFixed(2) : '0.00',
    avgEvents: total ? (eventSum/total).toFixed(2) : '0.00',
    failureTop: top,
  };
}
async function loadRuns(){
  const rsp = await fetch('/api/runs');
  const data = await rsp.json();
  allRuns = Array.isArray(data) ? data : [];
  const statusEl = document.getElementById('status');
  const keep = statusEl.value;
  const statusSet = new Set(allRuns.map((r)=>r.status||'unknown'));
  statusEl.innerHTML = '<option value="">All status</option>' + Array.from(statusSet).sort().map((s)=>`<option value="${s}">${s}</option>`).join('');
  if(keep){ statusEl.value = keep; }
  paint();
}
document.getElementById('q').addEventListener('input', paint);
document.getElementById('status').addEventListener('change', paint);
document.getElementById('sort').addEventListener('change', paint);
document.getElementById('refresh').addEventListener('click', ()=>loadRuns().catch((e)=>{document.getElementById('runs').innerHTML=`<div class="empty">Load failed: ${e}</div>`;}));
setInterval(()=>{ if(document.getElementById('auto').checked){ loadRuns().catch(()=>{}); } }, 2500);
loadRuns().catch((e)=>{document.getElementById('runs').innerHTML=`<div class="empty">Load failed: ${e}</div>`;});
</script>
</body></html>"""


def _render_not_found(run_id: str) -> str:
    safe = html.escape(run_id)
    return f"""<!doctype html><html><head><meta charset="utf-8"/><title>run not found</title></head>
<body style="font-family:ui-sans-serif,system-ui;background:#101522;color:#dfe8fb;padding:24px">
<h2>Run not found: {safe}</h2><a href="/" style="color:#83c4ff">Back to board</a></body></html>"""


def _render_run_html(payload: Dict[str, Any], embedded: bool) -> str:
    run_id = html.escape(str(payload.get("run_id", "")))
    run_path = html.escape(str(payload.get("run", "")))
    manifest = html.escape(json.dumps(payload.get("manifest", {}), ensure_ascii=False, indent=2))
    payload_json = _json_for_script(payload)
    buttons = ""
    if not embedded:
        buttons = (
            f'<a class="btn" href="/export/raw/{run_id}">export raw</a>'
            f'<a class="btn" href="/export/html/{run_id}">export html</a>'
            f'<a class="btn" href="/replay/{run_id}">replay</a>'
            '<a class="btn ghost" href="/">board</a>'
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>qita run {run_id}</title>
<style>
:root{{--bg:#090d16;--panel:#111a2c;--line:#223352;--txt:#e7edf9;--muted:#a7b8da;--accent:#50b6ff}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(160deg,#0a0f1d,#0a152b);color:var(--txt);font-family:ui-sans-serif,system-ui}}
.wrap{{max-width:1460px;margin:0 auto;padding:18px}}
.top{{position:sticky;top:0;background:rgba(9,13,22,.9);backdrop-filter:blur(8px);padding:12px 0 14px;z-index:10;border-bottom:1px solid var(--line)}}
.title{{font-size:22px;font-weight:800}} .muted{{color:var(--muted);font-size:12px}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}
.btn{{display:inline-block;border:1px solid var(--line);padding:7px 11px;border-radius:8px;text-decoration:none;color:var(--txt);background:#172643;font-size:12px}}
.btn:hover{{border-color:var(--accent)}} .btn.ghost{{background:transparent}}
.layout{{display:grid;grid-template-columns:260px 1fr;gap:12px;margin-top:12px}}
.side{{position:sticky;top:84px;height:calc(100vh - 120px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px}}
.main{{min-width:0}}
.manifest{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin-top:0}}
.tabs{{display:flex;gap:8px;margin-bottom:10px}}
.tab{{border:1px solid var(--line);background:#0f1930;color:var(--txt);padding:8px 12px;border-radius:999px;cursor:pointer;font-size:13px}}
.tab.active{{background:#1a335b;border-color:var(--accent)}}
.panel{{display:none}}
.panel.active{{display:block}}
.controls{{display:grid;grid-template-columns:1.2fr .8fr .8fr .8fr .8fr auto auto auto;gap:8px;margin:12px 0}}
.controls input,.controls select{{border:1px solid var(--line);background:#0d1527;color:var(--txt);border-radius:8px;padding:8px 10px;font-size:12px}}
.overview{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin:10px 0 12px}}
.ov{{background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,0));border:1px solid #2a3d61;border-radius:10px;padding:8px 10px}}
.ov .k{{font-size:11px;color:#91a8d6;text-transform:uppercase;letter-spacing:.3px}}
.ov .v{{font-size:14px;color:#e7f0ff;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.timeline{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 12px}}
.trow{{display:grid;grid-template-columns:82px 1fr 64px;gap:8px;align-items:center;margin:6px 0}}
.tlabel{{font-size:12px;color:#9fb2d8}}
.track{{height:16px;background:#0b1220;border:1px solid #1c2b44;border-radius:999px;overflow:hidden;position:relative}}
.seg{{height:100%;display:inline-block}}
.heat0{{filter:brightness(0.85)}} .heat1{{filter:brightness(1)}} .heat2{{filter:brightness(1.15)}} .heat3{{filter:brightness(1.3)}}
.tdur{{font-size:11px;color:#9fb2d8;text-align:right}}
.flow{{display:grid;grid-template-columns:1fr;gap:12px}}
@media (max-width:1180px){{.layout{{grid-template-columns:1fr}} .side{{position:relative;top:0;height:auto}} .controls{{grid-template-columns:1fr 1fr}}}}
.card{{break-inside:avoid;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 12px;box-shadow:0 8px 20px rgba(0,0,0,.2)}}
.kind-thinking{{border-left:4px solid #9b8cff}} .kind-action{{border-left:4px solid #3dd68c}}
.kind-observation{{border-left:4px solid #4db5ff}} .kind-critic{{border-left:4px solid #f7b955}}
.kind-other{{border-left:4px solid #7287ad}}
.card-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.step{{font-weight:800}}
h4{{margin:8px 0 6px;font-size:12px;color:#95add8;text-transform:uppercase;letter-spacing:.3px;display:flex;justify-content:space-between;align-items:center}}
pre{{margin:0;background:#0b1220;border:1px solid #1c2b44;padding:10px;border-radius:8px;max-height:300px;overflow:auto;white-space:pre-wrap;word-break:break-word;color:#dde7fb;font-size:12px}}
.sbtn{{border:1px solid var(--line);background:#15233f;color:var(--txt);padding:2px 6px;border-radius:6px;font-size:11px;cursor:pointer}}
.kv{{display:grid;grid-template-columns:120px 1fr;gap:6px 10px;background:#0b1220;border:1px solid #1c2b44;padding:8px;border-radius:8px}}
.k{{font-size:11px;color:#8ea4cf;text-transform:uppercase;letter-spacing:.3px}}
.v{{font-size:12px;color:#dce8ff;word-break:break-word}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}}
.chip{{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid #294064;background:#0e1a30;color:#b8cdf4}}
.list{{display:grid;gap:8px}}
.item{{background:#0b1220;border:1px solid #1c2b44;border-radius:8px;padding:8px}}
.raw{{margin-top:6px}}
.tree-wrap{{margin-top:8px}}
.tree{{border:1px solid #1c2b44;border-radius:8px;padding:8px;background:#0b1220}}
.tree details{{margin:4px 0}}
.tree summary{{cursor:pointer;color:#b7cdf4;font-size:12px}}
.tree-children{{margin-left:10px;border-left:1px dashed #2a3d61;padding-left:10px}}
.tree-leaf{{display:grid;grid-template-columns:130px 1fr;gap:8px;margin:4px 0}}
.tree-key{{font-size:12px;color:#90a8d6}}
.tree-val{{font-size:12px;color:#e4edff;word-break:break-word}}
.toc-item{{display:block;width:100%;text-align:left;border:1px solid var(--line);background:#0f1930;color:var(--txt);padding:7px 8px;border-radius:8px;font-size:12px;cursor:pointer;margin-bottom:6px}}
.toc-item:hover{{border-color:var(--accent)}} .toc-item.active{{border-color:var(--accent);background:#173056}}
</style></head><body>
<div class="top"><div class="wrap">
  <div class="title">QitOS Trace · {run_id}</div>
  <div class="muted">{run_path}</div>
  <div class="toolbar">{buttons}</div>
</div></div>
<div class="wrap">
  <div class="layout">
    <aside class="side">
      <div style="font-size:12px;color:#9fb2d8;margin-bottom:8px">Step Navigator</div>
      <div id="toc"></div>
    </aside>
    <section class="main">
      <div class="tabs">
        <button class="tab active" id="tabTraj" type="button">Traj</button>
        <button class="tab" id="tabManifest" type="button">Manifest</button>
      </div>
      <section class="panel active" id="panelTraj">
        <section class="overview" id="overview"></section>
        <div class="controls">
          <input id="q" placeholder="Filter by text in observation/decision/action/critic/events"/>
          <select id="eventFilter"><option value="">All events</option></select>
          <select id="sort"><option value="asc">step asc</option><option value="desc">step desc</option></select>
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:#a7b8da"><input type="checkbox" id="showObs" checked/>obs</label>
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:#a7b8da"><input type="checkbox" id="showCritic" checked/>critic</label>
          <button class="btn" id="foldAll" type="button">Fold all</button>
          <button class="btn" id="fontDown" type="button">A-</button>
          <button class="btn" id="fontReset" type="button">A</button>
          <button class="btn" id="fontUp" type="button">A+</button>
        </div>
        <section class="timeline">
          <h4>phase timeline (gantt-like)</h4>
          <div id="timeline"></div>
        </section>
        <section class="flow" id="flow"></section>
      </section>
      <section class="panel" id="panelManifest">
        <section class="manifest"><h4>manifest</h4><pre>{manifest}</pre></section>
      </section>
    </section>
  </div>
</div>
<script id="payload" type="application/json">{payload_json}</script>
<script>
const payload = JSON.parse(document.getElementById('payload').textContent || '{{}}');
const steps = Array.isArray(payload.steps) ? payload.steps : [];
const eventsByStep = payload.events_by_step || {{}};
const flow = document.getElementById('flow');
const toc = document.getElementById('toc');
const timelineRoot = document.getElementById('timeline');
const overview = document.getElementById('overview');
const fontDownBtn = document.getElementById('fontDown');
const fontResetBtn = document.getElementById('fontReset');
const fontUpBtn = document.getElementById('fontUp');
const tabTraj = document.getElementById('tabTraj');
const tabManifest = document.getElementById('tabManifest');
const panelTraj = document.getElementById('panelTraj');
const panelManifest = document.getElementById('panelManifest');
let collapsedAll = false;
let fontScale = Number(localStorage.getItem('qita_view_font_scale') || '1.1');
let activeTab = localStorage.getItem('qita_view_tab') || 'traj';
function esc(s){{
  return String(s).replace(/[&<>]/g, function(c){{ return {{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]; }});
}}
function cardText(step, events){{
  return JSON.stringify(step).toLowerCase() + ' ' + JSON.stringify(events).toLowerCase();
}}
function toPreview(v){{
  if(v === null || v === undefined) return '-';
  if(typeof v === 'string') return v.length > 180 ? (v.slice(0, 180) + '...') : v;
  if(typeof v === 'number' || typeof v === 'boolean') return String(v);
  if(Array.isArray(v)) return '[' + v.length + ' items]';
  if(typeof v === 'object') return '{{...}}';
  return String(v);
}}
function kvRow(k, v){{
  return '<div class="k">'+esc(k)+'</div><div class="v">'+esc(toPreview(v))+'</div>';
}}
function kvBlock(rows){{
  return '<div class="kv">' + rows.join('') + '</div>';
}}
function truncateText(v, n){{
  const s = String(v === null || v === undefined ? '' : v);
  const lim = Number(n || 260);
  if(s.length <= lim) return s;
  return s.slice(0, lim) + '...';
}}
function shortUrl(url){{
  try {{
    const u = new URL(String(url));
    const p = u.pathname || '';
    return u.host + (p.length > 24 ? (p.slice(0, 24) + '...') : p);
  }} catch (_e) {{
    return truncateText(url, 36);
  }}
}}
function extractThought(decision, events){{
  if(decision && typeof decision === 'object' && typeof decision.rationale === 'string' && decision.rationale.trim()) {{
    return decision.rationale.trim();
  }}
  const es = Array.isArray(events) ? events : [];
  for(let i = es.length - 1; i >= 0; i -= 1){{
    const p = es[i] && es[i].payload;
    if(!p || typeof p !== 'object') continue;
    if(String(p.stage || '') !== 'model_output') continue;
    const raw = String(p.raw_output || '');
    if(!raw) continue;
    const m = raw.match(/Thought\\s*:\\s*([\\s\\S]*?)(?:\\n(?:Action|Final|Observation|Critic|Plan)\\s*:|$)/i);
    if(m && m[1]) return m[1].trim();
    return truncateText(raw, 220);
  }}
  return '';
}}
function firstActionLabel(actions){{
  if(!Array.isArray(actions) || !actions.length) return '';
  const a = actions[0] || {{}};
  const tool = a.tool || a.name || a.action || a.type || 'action';
  const args = (a.args && typeof a.args === 'object') ? a.args : (a.kwargs && typeof a.kwargs === 'object' ? a.kwargs : {{}});
  const pick = ['query','url','path','command','prompt','file'];
  const parts = [];
  for(const k of pick){{ if(k in args) parts.push(k + '=' + truncateText(args[k], 80)); }}
  if(!parts.length){{
    const ks = Object.keys(args);
    if(ks.length) parts.push(ks[0] + '=' + truncateText(args[ks[0]], 80));
  }}
  return parts.length ? (tool + '(' + parts.join(', ') + ')') : String(tool);
}}
function flattenResults(input){{
  const out = [];
  function walk(x, d){{
    if(d > 3) return;
    if(Array.isArray(x)){{ for(const it of x) walk(it, d + 1); return; }}
    if(!x || typeof x !== 'object') return;
    if(Array.isArray(x.results)) out.push(...x.results);
    if(Array.isArray(x.items)) out.push(...x.items);
    if(Array.isArray(x.search_results)) out.push(...x.search_results);
    for(const k of Object.keys(x)) walk(x[k], d + 1);
  }}
  walk(input, 0);
  return out;
}}
function renderSearchTable(rows){{
  if(!rows.length) return '';
  let h = '<table style="width:100%;border-collapse:collapse;font-size:12px;background:#0b1220;border:1px solid #1c2b44;border-radius:8px;overflow:hidden">';
  h += '<thead><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #1c2b44;color:#9fb2d8">Title</th><th style="text-align:left;padding:8px;border-bottom:1px solid #1c2b44;color:#9fb2d8">URL</th></tr></thead><tbody>';
  for(const r of rows.slice(0, 8)){{
    h += '<tr><td style="padding:8px;border-bottom:1px solid #1c2b44">'+esc(truncateText(r.title, 90))+'</td><td style="padding:8px;border-bottom:1px solid #1c2b44;color:#86c8ff">'+esc(shortUrl(r.url))+'</td></tr>';
  }}
  h += '</tbody></table>';
  return h;
}}
function renderState(obs){{
  if(!obs || typeof obs !== 'object') return '<div class="muted">No state.</div>';
  const observeOut = (obs.observe_output && typeof obs.observe_output === 'object') ? obs.observe_output : {{}};
  const parts = [];
  const keys = Object.keys(observeOut);
  for(const k of keys.slice(0, 12)){{
    if(['run_id','latency_ms','error_category','ts','step_id','phase'].includes(k)) continue;
    const v = observeOut[k];
    if(typeof v === 'object') continue;
    parts.push(kvRow(k, v));
  }}
  if(parts.length) return kvBlock(parts);
  return '<div class="muted">No scalar state fields.</div>';
}}
function renderDirectObservation(actionResults){{
  const ars = Array.isArray(actionResults) ? actionResults : [];
  if(!ars.length) return '<div class="muted">No direct observation from action.</div>';
  const flat = flattenResults(ars);
  const rows = [];
  for(const it of flat){{
    if(!it || typeof it !== 'object') continue;
    const title = it.title || it.name || '';
    const url = it.url || it.link || it.href || '';
    if(title && url) rows.push({{title:String(title), url:String(url)}});
  }}
  const table = renderSearchTable(rows);
  if(table) return table;
  const first = ars[0];
  if(first && typeof first === 'object' && 'error' in first){{
    return '<div style="color:#ff8a8a"><b>[✘] Error:</b> ' + esc(truncateText(first.error, 220)) + '</div>';
  }}
  return '<pre>' + esc(JSON.stringify(first, null, 2).slice(0, 1200)) + (JSON.stringify(first).length > 1200 ? '\\n... (truncated)' : '') + '</pre>';
}}
function renderThought(decision, events){{
  const thought = extractThought(decision, events);
  if(!thought) return '<div class="muted">No explicit thought.</div>';
  return '<div style="white-space:pre-wrap;line-height:1.6;background:#0b1220;border:1px solid #1c2b44;border-radius:8px;padding:10px;color:#cfe6ff">'+esc(thought)+'</div>';
}}
function renderAction(actions){{
  const label = firstActionLabel(actions);
  if(!label) return '<div class="muted">No action.</div>';
  return '<div style="font-size:13px;color:#f4df8f">🛠️ <b>Action:</b> ' + esc(label) + '</div>';
}}
function renderMemoryUpdate(observeOut){{
  const mem = observeOut && typeof observeOut === 'object' ? observeOut.memory : null;
  if(!mem || typeof mem !== 'object') return '<div class="muted">No memory update.</div>';
  const rows = [];
  if('enabled' in mem) rows.push(kvRow('enabled', mem.enabled));
  if(Array.isArray(mem.records)) rows.push(kvRow('records', mem.records.length));
  if(typeof mem.summary === 'string' && mem.summary.trim()) rows.push(kvRow('summary', truncateText(mem.summary, 220)));
  return rows.length ? kvBlock(rows) : '<div class="muted">No memory update.</div>';
}}
function renderCritic(data){{
  if(!Array.isArray(data) || !data.length) return '<div class="muted">No critic outputs.</div>';
  const first = data[0];
  if(first && typeof first === 'object'){{
    const rows = [];
    if('action' in first) rows.push(kvRow('action', first.action));
    if('reason' in first) rows.push(kvRow('reason', first.reason));
    if('score' in first) rows.push(kvRow('score', first.score));
    return kvBlock(rows.length ? rows : [kvRow('critic', JSON.stringify(first))]);
  }}
  return kvBlock([kvRow('critic', first)]);
}}
function renderEvents(events){{
  if(!Array.isArray(events) || !events.length) return '<div class="muted">No events.</div>';
  const items = [];
  for(const e of events){{
    items.push('<div class="item">' + kvBlock([
      kvRow('phase', e.phase || ''),
      kvRow('ok', e.ok),
      kvRow('error', e.error || ''),
    ]) + '</div>');
  }}
  return '<div class="list">' + items.join('') + '</div>';
}}
function sectionHtml(title, bodyHtml, rawData, key, collapsed){{
  const txt = esc(JSON.stringify(rawData, null, 2));
  const isCollapsed = !!collapsed;
  const display = isCollapsed ? 'none' : 'block';
  const btn = isCollapsed ? 'expand' : 'collapse';
  const tree = '<details class="tree-wrap"><summary class="muted">Structured View</summary>' + renderTree(rawData) + '</details>';
  return '<section data-key="' + key + '" style="display:' + display + '">' +
    '<h4>' + title + ' <button class="sbtn tgl" data-key="' + key + '" type="button">' + btn + '</button></h4>' +
    bodyHtml +
    tree +
    '<details class="raw"><summary class="muted">Raw JSON</summary><pre>' + txt + '</pre></details></section>';
}}
function applyFontScale(){{
  if(!Number.isFinite(fontScale)) fontScale = 1.1;
  fontScale = Math.max(0.8, Math.min(2.0, fontScale));
  document.body.style.zoom = String(fontScale);
  localStorage.setItem('qita_view_font_scale', String(fontScale));
}}
function applyTab(){{
  const traj = activeTab === 'traj';
  tabTraj.classList.toggle('active', traj);
  tabManifest.classList.toggle('active', !traj);
  panelTraj.classList.toggle('active', traj);
  panelManifest.classList.toggle('active', !traj);
  localStorage.setItem('qita_view_tab', activeTab);
}}
function typeName(v){{
  if(v === null) return 'null';
  if(Array.isArray(v)) return 'array';
  return typeof v;
}}
function treeLeaf(key, val){{
  return '<div class="tree-leaf"><div class="tree-key">'+esc(key)+'</div><div class="tree-val">'+esc(toPreview(val))+'</div></div>';
}}
function treeNode(key, val, depth){{
  const t = typeName(val);
  if(t !== 'object' && t !== 'array') return treeLeaf(key, val);
  const open = depth < 2 ? ' open' : '';
  if(t === 'array'){{
    const n = val.length;
    const lim = Math.min(n, 80);
    let inner = '';
    for(let i=0;i<lim;i+=1) inner += treeNode('[' + i + ']', val[i], depth + 1);
    if(n > lim) inner += treeLeaf('...', '+' + (n - lim) + ' more items');
    return '<details'+open+'><summary>'+esc(key)+' <span class="muted">array(' + n + ')</span></summary><div class="tree-children">' + inner + '</div></details>';
  }}
  const ks = Object.keys(val);
  const lim = Math.min(ks.length, 80);
  let inner = '';
  for(let i=0;i<lim;i+=1){{ const k = ks[i]; inner += treeNode(k, val[k], depth + 1); }}
  if(ks.length > lim) inner += treeLeaf('...', '+' + (ks.length - lim) + ' more keys');
  return '<details'+open+'><summary>'+esc(key)+' <span class="muted">object(' + ks.length + ')</span></summary><div class="tree-children">' + inner + '</div></details>';
}}
function renderTree(data){{
  return '<div class="tree">' + treeNode('value', data, 0) + '</div>';
}}
function parseTs(ts){{
  const v = Date.parse(String(ts||''));
  return Number.isNaN(v) ? null : v;
}}
function phaseColor(phase){{
  const p = String(phase||'').toLowerCase();
  if(p.includes('observe')) return '#4db5ff';
  if(p.includes('decide') || p.includes('model')) return '#9b8cff';
  if(p.includes('action') || p.includes('tool')) return '#3dd68c';
  if(p.includes('critic') || p.includes('reflect')) return '#f7b955';
  if(p.includes('memory')) return '#46d1c2';
  if(p.includes('done') || p.includes('stop')) return '#ff8c8c';
  return '#7f92b8';
}}
function inferPrimaryKind(events){{
  const es = Array.isArray(events) ? events : [];
  for(let i = es.length - 1; i >= 0; i -= 1){{
    const p = String(es[i] && es[i].phase || '').toLowerCase();
    if(p.includes('critic')) return 'critic';
    if(p.includes('act') || p.includes('tool')) return 'action';
    if(p.includes('observe')) return 'observation';
    if(p.includes('decide') || p.includes('model')) return 'thinking';
  }}
  return 'other';
}}
function paintOverview(items){{
  const m = payload.manifest || {{}};
  const s = m.summary || {{}};
  const total = items.length;
  const avgEvents = total ? (items.reduce((a,it)=>a + (it.events||[]).length, 0) / total).toFixed(1) : '0.0';
  overview.innerHTML = [
    ['run', payload.run_id || '-'],
    ['status', m.status || '-'],
    ['stop', s.stop_reason || '-'],
    ['steps', String(total)],
    ['avg events/step', String(avgEvents)],
    ['model', m.model_id || '-'],
  ].map(([k,v])=>'<div class="ov"><div class="k">'+esc(k)+'</div><div class="v">'+esc(v)+'</div></div>').join('');
}}
function buildTimeline(items){{
  const rows = [];
  for(const it of items){{
    const evs = (it.events || []).slice().sort(function(a,b){{
      const ta = parseTs(a.ts); const tb = parseTs(b.ts);
      if(ta === null && tb === null) return 0;
      if(ta === null) return 1;
      if(tb === null) return -1;
      return ta - tb;
    }});
    if(!evs.length) continue;
    const marks = evs.map(function(e){{ return parseTs(e.ts); }}).filter(function(x){{ return x !== null; }});
    const first = marks.length ? Math.min.apply(null, marks) : null;
    const last = marks.length ? Math.max.apply(null, marks) : null;
    const total = (first !== null && last !== null && last > first) ? (last - first) : null;
    const segs = [];
    for(let i=0;i<evs.length;i+=1){{
      const e = evs[i];
      const t0 = parseTs(e.ts);
      const t1 = (i+1<evs.length) ? parseTs(evs[i+1].ts) : t0;
      let dur = 100;
      if(t0 !== null && t1 !== null && t1 >= t0) dur = Math.max(20, t1 - t0);
      if(total && t0 !== null && t1 !== null && t1 >= t0){{
        dur = Math.max(2, ((t1 - t0) / total) * 100);
      }}
      let heat = 'heat0';
      if(dur > 40) heat = 'heat3';
      else if(dur > 20) heat = 'heat2';
      else if(dur > 8) heat = 'heat1';
      segs.push('<span class="seg '+heat+'" title="'+esc((e.phase||'unknown') + ' · ' + String(e.ts||''))+'" style="width:'+dur+'%;background:'+phaseColor(e.phase)+'"></span>');
    }}
    const d = total !== null ? (total + 'ms') : '-';
    rows.push('<div class="trow"><div class="tlabel">STEP '+it.sid+'</div><div class="track">'+segs.join('')+'</div><div class="tdur">'+d+'</div></div>');
  }}
  timelineRoot.innerHTML = rows.join('') || '<div class="muted">No event timing data.</div>';
}}
function render(){{
  const q = (document.getElementById('q').value||'').toLowerCase();
  const eventFilter = document.getElementById('eventFilter').value;
  const sort = document.getElementById('sort').value;
  const showObs = document.getElementById('showObs').checked;
  const showCritic = document.getElementById('showCritic').checked;
  let items = steps.map(function(s){{ return {{step:s, sid:String(s.step_id), events:(eventsByStep[String(s.step_id)]||[])}}; }});
  if(eventFilter) items = items.filter(function(it){{ return it.events.some(function(e){{ return String(e.phase||'')===eventFilter; }}); }});
  if(q) items = items.filter(function(it){{ return cardText(it.step,it.events).includes(q); }});
  items.sort(function(a,b){{ return sort==='desc' ? Number(b.sid)-Number(a.sid) : Number(a.sid)-Number(b.sid); }});
  paintOverview(items);
  buildTimeline(items);
  flow.innerHTML = '';
  toc.innerHTML = '';
  for(const it of items){{
    const d = it.step.decision || {{}};
    const obsInput = {{
      observe_output: it.step.observation || {{}},
    }};
    const card = document.createElement('article');
    card.className = 'card kind-' + inferPrimaryKind(it.events);
    card.id = 'step-' + it.sid;
    let h = '<div class="card-head"><div class="step">STEP ' + it.sid + '</div><div class="muted">events ' + it.events.length + '</div></div>';
    if(showObs) h += sectionHtml('State', renderState(obsInput), obsInput, 'state', collapsedAll);
    h += sectionHtml('Thought', renderThought(d, it.events), d, 'thought', collapsedAll);
    h += sectionHtml('Action', renderAction(it.step.actions||[]), it.step.actions||[], 'action', collapsedAll);
    h += sectionHtml('Direct Observation', renderDirectObservation(it.step.action_results||[]), it.step.action_results||[], 'direct_observation', collapsedAll);
    h += sectionHtml('Memory Update', renderMemoryUpdate(obsInput.observe_output || {{}}), obsInput.observe_output || {{}}, 'memory', collapsedAll);
    if(showCritic) h += sectionHtml('Critic', renderCritic(it.step.critic_outputs||[]), it.step.critic_outputs||[], 'critic', collapsedAll);
    h += sectionHtml('Trace Events', renderEvents(it.events), it.events, 'events', true);
    card.innerHTML = h;
    flow.appendChild(card);
    const b = document.createElement('button');
    b.className = 'toc-item';
    b.type = 'button';
    b.textContent = 'STEP ' + it.sid;
    b.onclick = function(){{ const target = document.getElementById('step-' + it.sid); if(target) target.scrollIntoView({{behavior:'smooth',block:'start'}}); highlightToc(b); }};
    toc.appendChild(b);
  }}
  const phases = new Set();
  for(const s of steps){{
    const es = eventsByStep[String(s.step_id)] || [];
    for(const e of es){{ if(e.phase) phases.add(String(e.phase)); }}
  }}
  const ef = document.getElementById('eventFilter');
  const keep = ef.value;
  ef.innerHTML = '<option value="">All events</option>';
  Array.from(phases).sort().forEach(function(p){{
    const op = document.createElement('option');
    op.value = p;
    op.textContent = p;
    ef.appendChild(op);
  }});
  if(keep) ef.value = keep;
}}
function highlightToc(el){{
  document.querySelectorAll('.toc-item').forEach(function(x){{ x.classList.remove('active'); }});
  el.classList.add('active');
}}
document.getElementById('q').addEventListener('input', render);
document.getElementById('eventFilter').addEventListener('change', render);
document.getElementById('sort').addEventListener('change', render);
document.getElementById('showObs').addEventListener('change', render);
document.getElementById('showCritic').addEventListener('change', render);
document.getElementById('foldAll').addEventListener('click', function(){{
  collapsedAll = !collapsedAll;
  document.getElementById('foldAll').textContent = collapsedAll ? 'Expand all' : 'Fold all';
  render();
}});
fontDownBtn.addEventListener('click', function(){{ fontScale -= 0.1; applyFontScale(); }});
fontUpBtn.addEventListener('click', function(){{ fontScale += 0.1; applyFontScale(); }});
fontResetBtn.addEventListener('click', function(){{ fontScale = 1.1; applyFontScale(); }});
tabTraj.addEventListener('click', function(){{ activeTab = 'traj'; applyTab(); }});
tabManifest.addEventListener('click', function(){{ activeTab = 'manifest'; applyTab(); }});
document.addEventListener('click', function(e){{
  const t = e.target;
  if(!(t instanceof HTMLElement)) return;
  if(!t.classList.contains('tgl')) return;
  const secEl = t.closest('section');
  if(!secEl) return;
  const hidden = secEl.style.display === 'none';
  secEl.style.display = hidden ? 'block' : 'none';
  t.textContent = hidden ? 'collapse' : 'expand';
}});
applyFontScale();
applyTab();
render();
</script>
</body></html>"""


def _json_for_script(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    return raw.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _build_replay_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = payload.get("steps") or []
    events = payload.get("events") or []
    records: List[Dict[str, Any]] = []
    for ev in events:
        sid = ev.get("step_id")
        phase = str(ev.get("phase", "unknown"))
        node = str(ev.get("node", ""))
        kind = _infer_kind(phase, node, ev.get("error"))
        step = _find_step(steps, sid) or {}
        body = {
            "event": ev,
            "observation": step.get("observation", {}),
            "decision": step.get("decision", {}),
            "actions": step.get("actions", []),
            "action_results": step.get("action_results", []),
            "critic_outputs": step.get("critic_outputs", []),
        }
        records.append(
            {
                "step_id": sid,
                "phase": phase,
                "node": node,
                "kind": kind,
                "ok": ev.get("ok"),
                "error": ev.get("error"),
                "ts": ev.get("ts"),
                "title": f"[step={sid}] {phase}",
                "body": body,
            }
        )
    records.append(
        {
            "step_id": None,
            "phase": "DONE",
            "node": "engine",
            "kind": "done",
            "ok": True,
            "error": None,
            "ts": None,
            "title": "[done] replay completed",
            "body": {"summary": (payload.get("manifest") or {}).get("summary", {})},
        }
    )
    return records


def _infer_kind(phase: str, node: str, error: Any) -> str:
    if error:
        return "error"
    key = f"{phase} {node}".lower()
    if "plan" in key:
        return "plan"
    if "observe" in key:
        return "observation"
    if "memory" in key:
        return "memory"
    if "critic" in key or "reflect" in key:
        return "critic"
    if "action" in key or "tool" in key:
        return "action"
    if "decide" in key or "model" in key or "think" in key:
        return "thinking"
    if "done" in key or "stop" in key:
        return "done"
    return "event"


def _find_step(steps: List[Dict[str, Any]], step_id: Any) -> Optional[Dict[str, Any]]:
    for st in steps:
        if str(st.get("step_id")) == str(step_id):
            return st
    return None


def _render_replay_html(payload: Dict[str, Any], speed_ms: int) -> str:
    run_id = html.escape(str(payload.get("run_id", "")))
    records = json.dumps(_build_replay_records(payload), ensure_ascii=False)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>qita replay {run_id}</title>
<style>
:root{{--bg:#090d16;--txt:#e2f0ff;--muted:#8aa2c7;--line:#1f2f4d;--ok:#49df9a}}
body{{margin:0;background:radial-gradient(circle at 20% 0%,#12233f,#090d16 62%);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--txt)}}
.wrap{{max-width:1260px;margin:0 auto;padding:20px}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:10px;flex-wrap:wrap}}
.btn{{display:inline-block;border:1px solid var(--line);color:var(--txt);text-decoration:none;padding:6px 10px;border-radius:8px;background:#14223d;font-size:12px;cursor:pointer}}
.terminal{{background:#050a14;border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.bar{{background:#0b1528;border-bottom:1px solid var(--line);padding:8px 10px;color:var(--muted);font-size:12px;display:flex;justify-content:space-between;gap:10px;align-items:center}}
.stats{{display:flex;gap:8px;flex-wrap:wrap;padding:8px 10px;border-bottom:1px solid var(--line);background:#081021}}
.chip{{font-size:11px;color:#cde0ff;border:1px solid #28406a;border-radius:999px;padding:3px 8px;background:#0d1a31}}
.screen{{padding:14px;min-height:480px;display:grid;gap:10px}}
.card{{border:1px solid var(--line);background:#0a1224;border-radius:10px;padding:10px;box-shadow:0 6px 16px rgba(0,0,0,.25)}}
.ctitle{{font-size:12px;font-weight:700;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px}}
.tag{{font-size:10px;border:1px solid var(--line);padding:1px 6px;border-radius:999px;color:#a8bbdf}}
.kind-plan{{border-color:#8393ff}} .kind-thinking{{border-color:#ae8dff}} .kind-action{{border-color:#3dd68c}}
.kind-memory{{border-color:#46d1c2}} .kind-observation{{border-color:#4db5ff}} .kind-critic{{border-color:#f7b955}}
.kind-done{{border-color:#ff9d9d}} .kind-error{{border-color:#ff6b6b}}
.cbody{{white-space:pre-wrap;word-break:break-word;background:#081021;border:1px solid #1b2a44;padding:8px;border-radius:8px;font-size:12px}}
.cursor{{display:inline-block;width:8px;height:16px;background:var(--ok);margin-left:3px;animation:blink 1s steps(2,start) infinite}}
.ctl{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.ctl input,.ctl select{{background:#081021;border:1px solid var(--line);color:var(--txt);padding:4px 6px;border-radius:6px;font-size:12px}}
@keyframes blink{{to{{visibility:hidden}}}}
</style></head><body>
<div class="wrap">
  <div class="top"><div>QitOS Replay · {run_id}</div><div><a class="btn" href="/run/{run_id}">view</a> <a class="btn" href="/">board</a></div></div>
  <div class="terminal">
    <div class="bar">
      <span>qita replay</span>
      <div class="ctl">
        <button class="btn" id="play" type="button">Pause</button>
        <button class="btn" id="step" type="button">Step +1</button>
        <button class="btn" id="reset" type="button">Reset</button>
        <label>Speed
          <select id="speed">
            <option value="100">fast</option>
            <option value="250">normal</option>
            <option value="{int(speed_ms)}" selected>default</option>
            <option value="800">slow</option>
          </select>
        </label>
        <label><input type="checkbox" id="onlyErr"/>only errors</label>
        <label>breakpoint phase<input id="bp" placeholder="ACTION,CRITIC" style="width:150px"/></label>
        <label>Progress <input id="progress" type="range" min="0" max="0" value="0"/></label>
      </div>
    </div>
    <div class="stats" id="stats"></div>
    <div class="screen" id="screen"></div>
  </div>
</div>
<script>
const records = {records};
const screen = document.getElementById('screen');
const stats = document.getElementById('stats');
const progress = document.getElementById('progress');
const speedEl = document.getElementById('speed');
const playBtn = document.getElementById('play');
const stepBtn = document.getElementById('step');
const resetBtn = document.getElementById('reset');
const onlyErr = document.getElementById('onlyErr');
const bp = document.getElementById('bp');
let i = 0;
let playing = true;
let timer = null;
progress.max = String(Math.max(records.length, 1));
function esc(s){{ return String(s).replace(/[&<>]/g, function(c){{ return {{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]; }}); }}
function truncateText(v, n){{
  const s = String(v === null || v === undefined ? '' : v);
  const lim = Number(n || 260);
  return s.length <= lim ? s : (s.slice(0, lim) + '...');
}}
function thoughtFromDecision(d){{
  if(!d || typeof d !== 'object') return '';
  const r = d.rationale;
  if(typeof r !== 'string') return '';
  return truncateText(r, 260);
}}
function actionLabel(actions){{
  if(!Array.isArray(actions) || !actions.length) return '';
  const a = actions[0] || {{}};
  const tool = a.tool || a.name || a.action || a.type || 'action';
  const args = (a.args && typeof a.args === 'object') ? a.args : {{}};
  const ks = ['query','url','path','command','prompt','file'];
  const parts = [];
  for(const k of ks){{ if(k in args) parts.push(k + '=' + truncateText(args[k], 80)); }}
  return parts.length ? (tool + '(' + parts.join(', ') + ')') : String(tool);
}}
function stateSummary(observation){{
  if(!observation || typeof observation !== 'object') return 'No state.';
  const keep = [];
  const keys = Object.keys(observation);
  for(const k of keys){{
    if(['run_id','latency_ms','error_category','ts','step_id','phase'].includes(k)) continue;
    const v = observation[k];
    if(typeof v === 'object') continue;
    keep.push(k + '=' + truncateText(v, 60));
    if(keep.length >= 6) break;
  }}
  return keep.length ? keep.join(' · ') : 'No scalar state fields.';
}}
function observationSummary(actionResults){{
  if(!Array.isArray(actionResults) || !actionResults.length) return 'No observation.';
  const first = actionResults[0];
  if(first && typeof first === 'object'){{
    if(Array.isArray(first.results) && first.results.length){{
      const r = first.results[0] || {{}};
      const t = r.title || r.name || '';
      const u = r.url || r.link || r.href || '';
      if(t || u) return truncateText((t ? t + ' · ' : '') + u, 180);
    }}
    if('error' in first) return 'error: ' + truncateText(first.error, 180);
  }}
  return truncateText(JSON.stringify(first), 180);
}}
function criticSummary(cs){{
  if(!Array.isArray(cs) || !cs.length) return 'No critic output.';
  const c = cs[0];
  if(c && typeof c === 'object'){{
    const action = c.action ? ('action=' + c.action + ' ') : '';
    const reason = c.reason ? ('reason=' + truncateText(c.reason, 180)) : truncateText(JSON.stringify(c), 180);
    return action + reason;
  }}
  return truncateText(c, 180);
}}
function renderRecordBody(r){{
  const phase = String(r.phase||'').toLowerCase();
  if(phase.includes('observe')) return '🧭 <b>State:</b> ' + esc(stateSummary(r.body && r.body.observation));
  if(r.kind === 'thinking') return '🧠 <b>Thought:</b> ' + esc(thoughtFromDecision(r.body && r.body.decision));
  if(r.kind === 'action') return '🛠️ <b>Action:</b> ' + esc(actionLabel(r.body && r.body.actions)) + '<br/>✅ <b>Direct Observation:</b> ' + esc(observationSummary(r.body && r.body.action_results));
  if(r.kind === 'observation') return '✅ <b>Direct Observation:</b> ' + esc(observationSummary(r.body && r.body.action_results));
  if(r.kind === 'memory') return '💾 <b>Memory Update:</b> ' + esc('memory context updated');
  if(r.kind === 'critic') return '🧪 <b>Critic:</b> ' + esc(criticSummary(r.body && r.body.critic_outputs));
  if(r.kind === 'done') return '🏁 <b>Done:</b> ' + esc(truncateText(JSON.stringify((r.body && r.body.summary) || {{}}), 220));
  if(r.error) return '❌ <b>Error:</b> ' + esc(truncateText(r.error, 220));
  return esc(truncateText(r.title || '', 220));
}}
function fmt(r){{
  const err = r.error ? '<span class="tag kind-error">error</span>' : '';
  const raw = esc(JSON.stringify(r.body, null, 2));
  return '<article class="card kind-'+esc(r.kind)+'">' +
    '<div class="ctitle"><span>'+esc(r.title)+'</span><span><span class="tag">'+esc(r.phase||'')+'</span> <span class="tag kind-'+esc(r.kind)+'">'+esc(r.kind)+'</span> '+err+'</span></div>' +
    '<div class="cbody">'+renderRecordBody(r)+'</div>' +
    '<details style="margin-top:8px"><summary style="cursor:pointer;color:#8aa2c7">Raw</summary><pre style="white-space:pre-wrap;background:#081021;border:1px solid #1b2a44;border-radius:8px;padding:8px">'+raw+'</pre></details>' +
    '</article>';
}}
function shouldShow(r){{
  if(onlyErr.checked && !r.error) return false;
  return true;
}}
function hitBreakpoint(r){{
  const raw = String(bp.value||'').trim();
  if(!raw) return false;
  const set = new Set(raw.split(',').map(function(x){{ return x.trim().toLowerCase(); }}).filter(Boolean));
  return set.has(String(r.phase||'').toLowerCase());
}}
function render(){{
  const shown = records.slice(0, i).filter(shouldShow);
  const errCount = shown.filter((r)=>!!r.error).length;
  const kindMap = new Map();
  for(const r of shown){{ kindMap.set(r.kind, (kindMap.get(r.kind)||0)+1); }}
  const kindText = Array.from(kindMap.entries()).slice(0,6).map(([k,v])=>k+':'+v).join(' · ') || '-';
  stats.innerHTML =
    '<span class="chip">shown: '+shown.length+'</span>' +
    '<span class="chip">errors: '+errCount+'</span>' +
    '<span class="chip">cursor: '+i+'/'+records.length+'</span>' +
    '<span class="chip">kinds: '+esc(kindText)+'</span>';
  screen.innerHTML = shown.map(fmt).join('') + (i >= records.length ? '<span class="cursor"></span>' : '');
  progress.value = String(i);
  window.scrollTo(0, document.body.scrollHeight);
}}
function tick(){{
  if(!playing) return;
  if(i >= records.length){{ render(); return; }}
  if(hitBreakpoint(records[i])){{ playing = false; playBtn.textContent = 'Play'; render(); return; }}
  i += 1;
  render();
  timer = setTimeout(tick, Number(speedEl.value || {int(speed_ms)}));
}}
playBtn.onclick = ()=>{{ playing = !playing; playBtn.textContent = playing ? 'Pause' : 'Play'; if(playing) tick(); }};
stepBtn.onclick = ()=>{{ i = Math.min(records.length, i + 1); render(); }};
resetBtn.onclick = ()=>{{ i = 0; render(); if(playing) tick(); }};
progress.oninput = ()=>{{ i = Number(progress.value || 0); render(); }};
speedEl.onchange = ()=>{{ if(playing){{ clearTimeout(timer); tick(); }} }};
onlyErr.onchange = render;
tick();
</script></body></html>"""
