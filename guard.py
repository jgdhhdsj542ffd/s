"""Super JinX guard: watcher bots that fix each part on its own (no full restart) + /jx-status.
Panel mode bots: nginx, panel, core (node), configs (5 xray ports), tunnel (real WebSocket handshake through nginx),
bootstrap (auto-setup service), ram, database (check + backup). Location mode: nginx, core, configs, tunnel, ram.
Speed settings are never touched."""
import glob, json, os, re, socket, sqlite3, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.getenv("JINX_DATA", "/var/lib/pasarguard")
RUN = os.getenv("JINX_RUN", "/run/jinx")
MODE = os.getenv("JINX_MODE", "panel").lower()
EDGE = int(os.getenv("PORT", "8080"))
PANEL, NODE, KEYSVC, STATUS_PORT = 8000, 62050, 8100, 8101
TICK = 15
GRACE = {"nginx": 20, "panel": 150, "node": 60}      # seconds after a (re)start before judging it
LIMIT = {"nginx": 3, "panel": 4, "node": 3}           # failed checks in a row before a fix
START = time.time()
LOCK = threading.Lock()
BOTS = {}

def log(*a): print("[guard]", *a, flush=True)

def bot(name):
    return BOTS.setdefault(name, {"ok": None, "fails": 0, "fixes": 0, "last_fix": 0, "hist": [], "note": ""})

def mark(name, ok, note=""):
    with LOCK:
        b = bot(name); b["ok"] = ok; b["note"] = note
        b["fails"] = 0 if ok else b["fails"] + 1
        return b["fails"]

# ---------------- process helpers (pid files are written by entrypoint.sh) ----------------
def pid_of(name):
    try: return int(open(f"{RUN}/{name}.pid").read().strip())
    except Exception: return None

def started_at(name):
    try: return os.path.getmtime(f"{RUN}/{name}.pid")
    except Exception: return START

def alive(p):
    try:
        with open(f"/proc/{p}/stat") as f: return f.read().split(")")[-1].split()[0] != "Z"
    except Exception: return False

def stop(p):
    if not p or not alive(p): return
    try: os.kill(p, 15)
    except Exception: return
    for _ in range(20):
        time.sleep(0.5)
        if not alive(p): return
    try: os.kill(p, 9)
    except Exception: pass

def stray_xray():
    """xray processes left behind by a dead node would keep ports 10001-10005 busy"""
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        try:
            cmd = open(f"{d}/cmdline", "rb").read().split(b"\0")[0].decode(errors="ignore")
            if os.path.basename(cmd) == "xray": out.append(int(d.rsplit("/", 1)[1]))
        except Exception: pass
    return out

def fix(name, why):
    """restart ONE part. The supervisor loop in entrypoint.sh starts it again within 3s."""
    b = bot(name)
    log(f"{name}: {why} -> restarting {name} only")
    stop(pid_of(name))
    if name == "node":
        time.sleep(1)
        for p in stray_xray(): stop(p)
    now = time.time()
    with LOCK:
        b["fixes"] += 1; b["last_fix"] = now; b["fails"] = 0
        b["hist"] = [t for t in b["hist"] if now - t < 900] + [now]
        if len(b["hist"]) >= 4:   # 4 fixes in 15 min did not help: let Railway restart the whole service
            log(f"{name}: still broken after 4 fixes in 15 min -> full service restart")
            open(f"{RUN}/fatal", "w").write(name)

def ready(name):
    return time.time() - max(started_at(name), bot(name)["last_fix"]) >= GRACE[name]

# ---------------- checks ----------------
def http_code(url, timeout=4):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "jinx-guard"}), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e: return e.code
    except Exception: return 0

def tcp(port, timeout=3):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout): return True
    except Exception: return False

def ws_probe(path, timeout=5):
    """the same handshake a phone does: GET <path> + Upgrade -> must answer 101 through nginx"""
    try:
        with socket.create_connection(("127.0.0.1", EDGE), timeout=timeout) as s:
            s.settimeout(timeout)
            crlf = chr(13) + chr(10)
            lines = [f"GET {path} HTTP/1.1", "Host: 127.0.0.1", "User-Agent: jinx-guard",
                     "Upgrade: websocket", "Connection: Upgrade",
                     "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Version: 13", "", ""]
            s.sendall(crlf.join(lines).encode())
            head = s.recv(64).decode(errors="ignore")
            return head.startswith("HTTP/1.1 101")
    except Exception: return False

def routes():
    """[(path, xray port)] from the nginx include written by genpaths.py"""
    try: txt = open(f"{DATA}/inbounds.inc").read()
    except Exception: return []
    return [(m.group(1), int(m.group(2))) for m in re.finditer(r"location = (\S+) \{ proxy_pass http://127\.0\.0\.1:(\d+);", txt)]

def memory():
    """(used_bytes, limit_bytes) of this container: anon memory, not page cache"""
    used = limit = 0
    for stat, lim, key in (("/sys/fs/cgroup/memory.stat", "/sys/fs/cgroup/memory.max", "anon"),
                           ("/sys/fs/cgroup/memory/memory.stat", "/sys/fs/cgroup/memory/memory.limit_in_bytes", "total_rss")):
        try:
            for line in open(stat):
                k, v = line.split()
                if k == key: used = int(v); break
            raw = open(lim).read().strip()
            limit = 0 if raw == "max" else int(raw)
            break
        except Exception: continue
    try:
        total = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1]) * 1024
        if not limit or limit > total: limit = total
    except Exception: pass
    return used, limit

# ---------------- bots ----------------
def bot_nginx():
    ok = http_code(f"http://127.0.0.1:{EDGE}/healthz") == 200
    n = mark("nginx", ok, "" if ok else f"port {EDGE} not answering")
    if not ok and n >= LIMIT["nginx"] and ready("nginx"): fix("nginx", f"port {EDGE} not answering")

def bot_panel():
    c = http_code(f"http://127.0.0.1:{PANEL}/api/system")
    ok = c in (200, 401, 403)
    n = mark("panel", ok, "" if ok else f"panel answer {c or 'none'}")
    if not ok and n >= LIMIT["panel"] and ready("panel"): fix("panel", f"panel answer {c or 'none'}")

def bot_node():
    ok = tcp(NODE)
    n = mark("node", ok, "" if ok else "core not listening")
    if not ok and n >= LIMIT["node"] and ready("node"): fix("node", "core not listening")

CFG = {"bad": 0}
def bot_configs():
    rs = routes()
    up = sum(1 for _, p in rs if tcp(p))
    ok = bool(rs) and up == len(rs)
    mark("configs", ok, f"{up}/{len(rs)} up")
    # judge only when the core itself is up and had time to load the configs from the panel
    if ok or not tcp(NODE) or time.time() - max(started_at("node"), bot("node")["last_fix"]) < 180:
        CFG["bad"] = 0; return
    CFG["bad"] += 1
    if CFG["bad"] >= 6:   # 6 x 30s = 3 min with configs down while core is up
        CFG["bad"] = 0; fix("node", f"configs down ({up}/{len(rs)})")

TUN = {"bad": 0}
def bot_tunnel():
    rs = routes(); fails = []
    for path, port in rs:
        if tcp(port) and not ws_probe(path): fails.append(port)
    ok = bool(rs) and not fails
    mark("tunnel", ok, "" if ok else f"{len(fails)} config(s) not passing nginx")
    if ok or not fails: TUN["bad"] = 0; return
    TUN["bad"] += 1
    if TUN["bad"] >= 3 and ready("nginx"):   # xray is fine but nginx does not pass the tunnel
        TUN["bad"] = 0; fix("nginx", "tunnel handshake failing")

def bot_bootstrap():
    ok = tcp(KEYSVC)
    mark("bootstrap", ok, "" if ok else "auto-setup restarting (fixes itself)")

RAM = {"last": 0}
def bot_ram():
    used, limit = memory()
    pct = round(used * 100 / limit, 1) if limit else 0
    with LOCK: bot("ram").update(used_mb=used // 2**20, limit_mb=limit // 2**20, pct=pct)
    mark("ram", pct < 90, f"{pct}%")
    if pct >= 92 and time.time() - RAM["last"] > 900:
        RAM["last"] = time.time(); fix("node", f"memory {pct}% -> gentle core restart before it runs out")

DBS = {"next": time.time() + 600}
def bot_db():
    db = f"{DATA}/db.sqlite3"
    if not os.path.exists(db): mark("database", None, "not created yet"); return
    con = None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        res = con.execute("PRAGMA quick_check").fetchone()[0]
        ok = res == "ok"
        if ok and time.time() >= DBS["next"]:
            DBS["next"] = time.time() + 6 * 3600
            size = os.path.getsize(db)
            st = os.statvfs(DATA)
            if st.f_bavail * st.f_frsize > size * 3:
                os.makedirs(f"{DATA}/backups", exist_ok=True)
                out = f"{DATA}/backups/db-{time.strftime('%Y%m%d-%H%M')}.sqlite3"
                dst = sqlite3.connect(out + ".tmp"); con.backup(dst); dst.close()
                os.replace(out + ".tmp", out)
                for old in sorted(glob.glob(f"{DATA}/backups/db-*.sqlite3"))[:-3]: os.remove(old)
                with LOCK: bot("database")["last_backup"] = os.path.basename(out)
                log("database backup saved:", os.path.basename(out))
        mark("database", ok, "" if ok else f"check: {res[:80]}")
    except Exception as e:
        mark("database", False, str(e)[:80])
    finally:
        if con is not None:
            try: con.close()
            except Exception: pass

ALL_JOBS = ((bot_nginx, 1), (bot_panel, 1), (bot_node, 1), (bot_bootstrap, 2), (bot_configs, 2),
            (bot_ram, 2), (bot_tunnel, 4), (bot_db, 20))
PANEL_ONLY = (bot_panel, bot_bootstrap, bot_db)
JOBS = tuple(j for j in ALL_JOBS if MODE != "node" or j[0] not in PANEL_ONLY)

def loop():
    i = 0
    while True:
        for job, every in JOBS:
            if i % every == 0:
                try: job()
                except Exception as e: log(job.__name__, "error:", e)
        i += 1
        time.sleep(TICK)

# ---------------- /jx-status ----------------
def status():
    with LOCK:
        parts = {k: {kk: vv for kk, vv in v.items() if kk not in ("hist", "last_fix", "fails")} for k, v in BOTS.items()}
    return {"ok": all(p["ok"] is not False for p in parts.values()), "mode": MODE,
            "region": os.getenv("RAILWAY_REPLICA_REGION", ""), "uptime_s": int(time.time() - START),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "parts": parts}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") != "/jx-status":
            self.send_response(404); self.end_headers(); return
        s = status(); data = json.dumps(s, ensure_ascii=False, indent=1).encode()
        self.send_response(200 if s["ok"] else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

def main():
    os.makedirs(RUN, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", STATUS_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"{len(JOBS)} guard bots on ({MODE} mode):", ", ".join(j[0].__name__[4:] for j in JOBS), "| /jx-status ready")
    time.sleep(10)
    loop()

if __name__ == "__main__":
    main()
