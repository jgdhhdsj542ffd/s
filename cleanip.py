"""Super JinX clean IP: configs that connect to a chosen edge IP instead of the domain.
- Anyone with a subscription link can upload IP files on their own subscription page (personal list).
- The owner can upload a list for everyone (API Keys > Owner access > Clean IP).
- Every IP is really tested from the server: TLS with SNI = panel domain + GET /healthz must reach THIS service.
  IPs that do not route to us are never used. Lists are re-tested every 6 hours, dead IPs drop out.
- Extra subscription link: /sub/<token>/jx-ip  (original link stays untouched, so nothing can break).
- Smart: every working IP also passes a real config handshake (WebSocket 101 on a config path), its country / city / ISP
  is found automatically, and if one of our locations is in that country the IP is pointed at that location.
- Watchdog: IPs in use are re-checked every 10 minutes; a dead one is dropped and the next best takes its place."""
import base64, hashlib, ipaddress, json, os, random, re, socket, ssl, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

DATA = os.getenv("JINX_DATA", "/var/lib/pasarguard")
DIR = f"{DATA}/cleanip"
BASE = "http://127.0.0.1:8000"
SUB_PATH = (os.getenv("SUBSCRIPTION_PATH") or "sub").strip("/")
MAX_CANDIDATES = 1500      # tested per upload
MAX_KEEP = 40              # working IPs kept per list
PORTS = (443, 2053, 2083, 2087, 2096, 8443)
WORKERS = 48
TIMEOUT = 3.0
RETEST = 2 * 3600          # full list
ACTIVE_RETEST = 600        # IPs that are on configs right now
GEO_TTL = 7 * 86400
LOCK = threading.Lock()
STORE_LOCK = threading.RLock()   # saved lists: owner save / remove / watchdog never overwrite each other
GEO_LOCK = threading.Lock()
JOBS = {}
_get_domain = lambda: ""
_get_places = lambda: []       # [(domain, cc, flag, name)] of the other live locations
_on_change = lambda: None      # the owner list changed by itself (watchdog): configs follow
_log = print

def init(get_domain, log, get_places=None, on_change=None):
    global _get_domain, _log, _get_places, _on_change
    _get_domain, _log = get_domain, log
    if get_places: _get_places = get_places
    if on_change: _on_change = on_change
    os.makedirs(DIR, exist_ok=True)
    threading.Thread(target=_retest_loop, daemon=True).start()

# ---------------- parsing uploads ----------------
_V4 = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}"
_TOK = re.compile(r"\[([0-9A-Fa-f:]{2,39})\](?::(\d{2,5}))?"                       # [v6]:port
                  r"|(?<![\w.:])(" + _V4 + r")(?:/(\d{1,2}))?(?::(\d{2,5}))?(?![\w.])"   # v4, v4/cidr, v4:port
                  r"|(?<![\w:])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})(?:/(\d{1,3}))?(?![\w:])")  # v6, v6/cidr

def parse(text, limit=MAX_CANDIDATES):
    """IPv4, IPv6, ip:port, [v6]:port, CIDR ranges, CSV/JSON lines from IP scanners. Private/odd IPs are dropped."""
    seen, out, ranges = set(), [], []
    for m in _TOK.finditer(str(text or "")[:600000]):
        if m.group(1): val, pre, port = m.group(1), None, m.group(2)
        elif m.group(3): val, pre, port = m.group(3), m.group(4), m.group(5)
        else: val, pre, port = m.group(6), m.group(7), None
        port = int(port or 443)
        if port not in PORTS: port = 443
        try:
            if pre:
                net = ipaddress.ip_network(f"{val}/{pre}", strict=False)
                if net.prefixlen < (16 if net.version == 4 else 112): continue
                ranges.append((net, port)); continue
            ip = ipaddress.ip_address(val)
        except ValueError:
            continue
        if not ip.is_global: continue
        k = (str(ip), port)
        if k not in seen: seen.add(k); out.append(k)
        if len(out) >= limit: return out
    # ranges: sample evenly so a /16 does not flood the tester
    for net, port in ranges:
        size = net.num_addresses
        n = min(size - 2 if size > 2 else size, 64)
        hosts = [net.network_address + random.randrange(1, max(2, size - 1)) for _ in range(n * 2)]
        for ip in hosts:
            k = (str(ip), port)
            if ipaddress.ip_address(ip).is_global and k not in seen:
                seen.add(k); out.append(k)
                n -= 1
                if n <= 0: break
    return out[:limit]

# ---------------- the real test ----------------
_CTX = ssl.create_default_context()
WHY = ("tcp", "tls", "http", "ws")    # where a bad IP failed: no connection / wrong certificate / not our service / config path

def _ws_path():
    """one real config path (clean IP twin) for the handshake test"""
    try:
        P = json.load(open(f"{DATA}/paths.json"))
        for t in ("JX-VLESS-WS-1-IP", "JX-VLESS-WS-2-IP", "JX-VLESS-WS-1"):
            if P.get(t): return P[t]
    except Exception: pass
    return None

def _recv_head(s, need=b"\r\n\r\n", limit=4096):
    buf = b""
    while len(buf) < limit:
        chunk = s.recv(1024)
        if not chunk: break
        buf += chunk
        if need in buf: break
    return buf

def check(ip, port, domain, ws_path=None):
    """(ms, None) when this IP serves OUR service for `domain` and a config handshake passes, else (None, why)"""
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    t0 = time.perf_counter()
    try:
        raw = socket.socket(fam, socket.SOCK_STREAM); raw.settimeout(TIMEOUT)
        raw.connect((ip, port))
    except Exception:
        return None, "tcp"
    try:
        try: s = _CTX.wrap_socket(raw, server_hostname=domain)
        except Exception: return None, "tls"
        with s:
            ms = int((time.perf_counter() - t0) * 1000)
            s.sendall(f"GET /healthz HTTP/1.1\r\nHost: {domain}\r\nUser-Agent: jinx-ip-test\r\n\r\n".encode())
            buf = _recv_head(s)
            head, _, body = buf.partition(b"\r\n\r\n")
            if len(body) < 2 and re.match(rb"HTTP/1\.[01] 200", head):
                try: body += s.recv(64)
                except Exception: pass
            if not (re.match(rb"HTTP/1\.[01] 200", head) and body.strip()[:2] == b"ok"): return None, "http"
            if ws_path and not _ws_ok(s, domain, ws_path):
                if not _ws_fresh(ip, port, domain, ws_path, fam): return None, "ws"   # retry on a fresh connection
            return ms, None
    except Exception:
        return None, "http"
    finally:
        try: raw.close()
        except Exception: pass

def _ws_ok(s, domain, ws_path):
    """the exact handshake a phone does on a config path: must answer 101"""
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET {ws_path} HTTP/1.1\r\nHost: {domain}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: jinx-ip-test\r\n\r\n").encode())
        return bool(re.match(rb"HTTP/1\.[01] 101", _recv_head(s)))
    except Exception: return False

def _ws_fresh(ip, port, domain, ws_path, fam):
    try:
        with socket.socket(fam, socket.SOCK_STREAM) as raw:
            raw.settimeout(TIMEOUT); raw.connect((ip, port))
            with _CTX.wrap_socket(raw, server_hostname=domain) as s: return _ws_ok(s, domain, ws_path)
    except Exception: return False

def probe(ip, port, domain):
    return check(ip, port, domain, _ws_path())[0]

def test_many(cands, domain, job=None, ws=True):
    """[{ip, port, ms}] best first. With a job: live counters, live best list and why the others failed."""
    res, path = [], (_ws_path() if ws else None)
    def one(c):
        ms, why = check(c[0], c[1], domain, path)
        if ms is not None:   # second try: the lower one is the real latency (first try pays DNS-less cold start)
            ms2, _ = check(c[0], c[1], domain, None)
            if ms2 is not None: ms = min(ms, ms2)
        if job is not None:
            with LOCK:
                job["tested"] += 1
                if ms is not None:
                    job["ok"] += 1; job["live"].append({"ip": c[0], "port": c[1], "ms": ms})
                    if len(job["live"]) > 60: job["live"].sort(key=lambda x: x["ms"]); del job["live"][30:]
                else:
                    job["fails"][why] = job["fails"].get(why, 0) + 1
                    if len(job["bad"]) < 60: job["bad"].append({"ip": c[0], "port": c[1], "why": why})
        return (c, ms)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for (ip, port), ms in ex.map(one, cands):
            if ms is not None: res.append({"ip": ip, "port": port, "ms": ms})
    res.sort(key=lambda x: x["ms"])
    return res

# ---------------- where is this IP? ----------------
FA = {"US": "آمریکا", "DE": "آلمان", "NL": "هلند", "GB": "انگلیس", "FR": "فرانسه", "SG": "سنگاپور", "JP": "ژاپن",
      "CA": "کانادا", "TR": "ترکیه", "AE": "امارات", "FI": "فنلاند", "SE": "سوئد", "CH": "سوئیس", "IT": "ایتالیا",
      "ES": "اسپانیا", "PL": "لهستان", "AT": "اتریش", "BE": "بلژیک", "IE": "ایرلند", "NO": "نروژ", "DK": "دانمارک",
      "RU": "روسیه", "IN": "هند", "HK": "هنگ‌کنگ", "KR": "کره جنوبی", "AU": "استرالیا", "BR": "برزیل", "CZ": "چک",
      "RO": "رومانی", "UA": "اوکراین", "AM": "ارمنستان", "GE": "گرجستان", "IR": "ایران", "IQ": "عراق", "QA": "قطر",
      "SA": "عربستان", "BH": "بحرین", "OM": "عمان", "KW": "کویت", "LU": "لوکزامبورگ", "PT": "پرتغال", "GR": "یونان",
      "HU": "مجارستان", "BG": "بلغارستان", "RS": "صربستان", "LT": "لیتوانی", "LV": "لتونی", "EE": "استونی",
      "MD": "مولداوی", "CY": "قبرس", "TW": "تایوان", "CN": "چین", "MY": "مالزی", "ID": "اندونزی", "TH": "تایلند",
      "VN": "ویتنام", "ZA": "آفریقای جنوبی", "MX": "مکزیک", "AR": "آرژانتین", "CL": "شیلی", "KZ": "قزاقستان",
      "AZ": "آذربایجان", "PK": "پاکستان", "AF": "افغانستان", "EG": "مصر", "IS": "ایسلند", "SK": "اسلواکی",
      "SI": "اسلوونی", "HR": "کرواسی", "AL": "آلبانی", "BA": "بوسنی", "MK": "مقدونیه", "BY": "بلاروس", "UZ": "ازبکستان",
      "TM": "ترکمنستان", "TJ": "تاجیکستان", "KG": "قرقیزستان", "PH": "فیلیپین", "NZ": "نیوزیلند", "MT": "مالت"}
GEO_FILE = f"{DIR}/geo.json"
_GEO = {}

def flag(cc):
    cc = (cc or "").upper()
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc) if re.fullmatch(r"[A-Z]{2}", cc) else ""

def cc_of_flag(f):
    try:
        cps = [ord(c) - 0x1F1E6 for c in (f or "") if 0x1F1E6 <= ord(c) <= 0x1F1FF]
        return "".join(chr(65 + c) for c in cps[:2]) if len(cps) >= 2 else ""
    except Exception: return ""

def _geo_load():
    global _GEO
    if not _GEO:
        try: _GEO = json.load(open(GEO_FILE))
        except Exception: _GEO = {}
    return _GEO

def _geo_save():
    try:
        with open(GEO_FILE + ".tmp", "w") as f: json.dump(_GEO, f)
        os.replace(GEO_FILE + ".tmp", GEO_FILE)
    except Exception: pass

def _http_json(url, data=None, timeout=6):
    r = urllib.request.Request(url, data=data, headers={"User-Agent": "super-jinx", "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp: return json.loads(resp.read().decode())

def geo_many(ips):
    """{ip: {cc, country, city, isp}} from cache, then ip-api (batch, 100 at a time), ipwho.is, country.is"""
    cache, now = _geo_load(), time.time()
    out, need = {}, []
    with GEO_LOCK: snap = dict(cache)
    for ip in dict.fromkeys(ips):
        g = snap.get(ip)
        if g and now - g.get("t", 0) < GEO_TTL: out[ip] = g
        else: need.append(ip)
    for i in range(0, len(need), 100):
        part = need[i:i + 100]
        try:
            res = _http_json("http://ip-api.com/batch?fields=status,query,countryCode,country,city,isp,org",
                             json.dumps(part).encode())
            for r in res if isinstance(res, list) else []:
                if r.get("status") == "success" and r.get("countryCode"):
                    out[r["query"]] = {"cc": r["countryCode"].upper(), "country": r.get("country", ""), "city": r.get("city", ""),
                                       "isp": (r.get("isp") or r.get("org") or "")[:60], "t": int(now)}
        except Exception as e:
            _log("IP location (ip-api):", e)
    for ip in [x for x in need if x not in out][:40]:
        g = None
        try:
            r = _http_json(f"https://ipwho.is/{ip}?fields=success,country_code,country,city,connection")
            if r.get("success") and r.get("country_code"):
                g = {"cc": r["country_code"].upper(), "country": r.get("country", ""), "city": r.get("city", ""),
                     "isp": ((r.get("connection") or {}).get("isp") or "")[:60]}
        except Exception: pass
        if not g:
            try:
                r = _http_json(f"https://api.country.is/{ip}")
                if r.get("country"): g = {"cc": r["country"].upper(), "country": "", "city": "", "isp": ""}
            except Exception: pass
        if g: g["t"] = int(now); out[ip] = g
    if need:
        with GEO_LOCK:
            for ip in need:
                if ip in out: cache[ip] = out[ip]
            if len(cache) > 5000:
                for k in sorted(cache, key=lambda k: cache[k].get("t", 0))[:1000]: cache.pop(k, None)
            _geo_save()
    return out

def place_of(cc):
    """a live location of ours in that country: (domain, name) or None"""
    if not cc: return None
    try:
        for d, lcc, fl, name in _get_places() or []:
            if lcc and lcc == cc and d: return d, name
    except Exception: pass
    return None

def enrich(results, main, job=None):
    """country / city / ISP for every working IP; IPs in a country where we have a location are pointed there
    (only if that location really answers through the IP, otherwise they stay on the main domain)"""
    if job is not None: job["phase"] = "geo"
    geo = geo_many([x["ip"] for x in results])
    path = _ws_path(); moved = []
    for x in results:
        g = geo.get(x["ip"]) or {}
        cc = g.get("cc", "")
        x.update({"cc": cc, "fa": FA.get(cc, g.get("country") or cc), "en": g.get("country") or cc,
                  "city": g.get("city", ""), "isp": g.get("isp", ""), "dom": None, "via": ""})
        p = place_of(cc)
        if p and p[0] != main: moved.append((x, p))
    if moved:
        if job is not None: job["phase"] = "loc"
        def one(xp):
            x, (d, name) = xp
            ms, _ = check(x["ip"], x["port"], d, path)
            if ms is not None: x["dom"], x["via"], x["ms"] = d, name, ms
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(moved))) as ex: list(ex.map(one, moved))
    results.sort(key=lambda x: x["ms"])
    return results

def start_job(scope, text):
    domain = _get_domain()
    if not domain: return None, "اول برای پنل دامنه بساز"
    cands = parse(text)
    if not cands: return None, "هیچ آی‌پی درستی توی فایل پیدا نشد"
    jid = hashlib.sha1(f"{scope}{time.time()}{random.random()}".encode()).hexdigest()[:12]
    job = {"scope": scope, "total": len(cands), "tested": 0, "ok": 0, "done": False, "results": [], "t": time.time(),
           "phase": "test", "live": [], "fails": {}, "bad": []}
    with LOCK:
        for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 1800 or v["scope"] == scope]: JOBS.pop(k, None)
        JOBS[jid] = job
    def run():
        try:
            res = test_many(cands, domain, job)[:200]
            try: res = enrich(res, domain, job)
            except Exception as e: _log("clean IP location:", e)
            job["results"] = res
        except Exception as e: _log("clean IP test:", e)
        finally: job["done"] = True
    threading.Thread(target=run, daemon=True).start()
    return jid, None

def job_status(scope, jid):
    j = JOBS.get(jid)
    if not j or j["scope"] != scope: return None
    with LOCK: live = sorted(j["live"], key=lambda x: x["ms"])[:8]
    return {"total": j["total"], "tested": j["tested"], "ok": j["ok"], "done": j["done"], "phase": j.get("phase", "test"),
            "live": live, "fails": j.get("fails", {}), "bad": j.get("bad", [])[:30],
            "results": j["results"] if j["done"] else []}

# ---------------- storage ----------------
def _path(scope): return f"{DIR}/{scope}.json"

def scope_of(token): return "u_" + hashlib.sha256(("jx-ip|" + token).encode()).hexdigest()[:32]

def load(scope):
    try:
        d = json.load(open(_path(scope), encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception: return None

KEEP = ("cc", "fa", "en", "city", "isp", "dom", "via")

def _store(scope, d):
    tmp = _path(scope) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, _path(scope))

def save(scope, ips, mode="both", per=2, share=None):
    clean = []
    for x in ips[:MAX_KEEP]:
        try:
            ip = str(ipaddress.ip_address(str(x.get("ip"))))
            port = int(x.get("port") or 443)
            if port not in PORTS: port = 443
            row = {"ip": ip, "port": port, "ms": int(x.get("ms") or 0), "fail": 0}
            for k in KEEP:
                if x.get(k) is not None: row[k] = str(x[k])[:80]
            clean.append(row)
        except Exception: continue
    with STORE_LOCK:
        return _save_locked(scope, clean, mode, per, share)

def _save_locked(scope, clean, mode, per, share):
    old = load(scope) or {}
    d = {"ips": clean, "mode": mode if mode in ("both", "ip") else "both", "per": max(1, min(10, int(per or 2))),
         "t": int(time.time()), "checked": int(time.time()), "achecked": int(time.time())}
    if scope == "global": d["share"] = bool(old.get("share", True) if share is None else share)
    _store(scope, d)
    return d

def remove_one(scope, ip, port):
    with STORE_LOCK: return _remove_locked(scope, ip, port)

def _remove_locked(scope, ip, port):
    d = load(scope)
    if not d: return {"count": 0}
    d["ips"] = [x for x in d["ips"] if not (x["ip"] == ip and int(x["port"]) == int(port))]
    if d["ips"]: _store(scope, d)
    else: clear(scope)
    return summary(scope)

def retest(scope, full=True):
    """re-check a saved list now (or only the IPs in use). Dead twice in a row -> out. Returns True if the list changed."""
    d = load(scope); dom = _get_domain()
    if not d or not dom or not d.get("ips"): return False
    ips = d["ips"] if full else d["ips"][:max(1, int(d.get("per") or 2))]
    path = _ws_path()
    def one(x):
        target = x.get("dom") or dom
        if x.get("dom") and not any(p[0] == x["dom"] for p in (_get_places() or [])): target = dom   # location gone
        ms, _ = check(x["ip"], x["port"], target, path)
        if ms is None and target != dom: ms, _ = check(x["ip"], x["port"], dom, path); target = dom if ms is not None else target
        return x, ms, target
    with ThreadPoolExecutor(max_workers=WORKERS) as ex: res = list(ex.map(one, ips))
    with STORE_LOCK:
        cur = load(scope)
        if not cur or cur.get("t") != d.get("t"): return False   # the owner changed the list meanwhile: keep theirs
        return _merge_retest(scope, d, res, dom, full)

def _merge_retest(scope, d, res, dom, full):
    before = [(x["ip"], x["port"], x.get("dom")) for x in d["ips"][:d.get("per", 2)]]
    if res and all(ms is None for _, ms, _ in res):
        # every IP failed at once: that is our side (service restarting / network hiccup), not the IPs -> keep the list
        d["achecked"] = int(time.time()); _store(scope, d)
        _log("clean IP check: no IP answered this round, list kept (will check again)")
        return False
    for x, ms, target in res:
        if ms is not None:
            x["ms"], x["fail"] = ms, 0
            if target != (x.get("dom") or dom):
                x["dom"] = None if target == dom else target
                if x["dom"] is None: x["via"] = ""
        else: x["fail"] = x.get("fail", 0) + 1
    keep = [x for x in d["ips"] if x.get("fail", 0) < 2]     # one bad check is forgiven, two in a row drops it
    missing = [x["ip"] for x in keep if not x.get("cc")]
    if missing:
        try:
            g = geo_many(missing)
            for x in keep:
                if x["ip"] in g and not x.get("cc"):
                    cc = g[x["ip"]].get("cc", ""); x.update({"cc": cc, "fa": FA.get(cc, g[x["ip"]].get("country") or cc),
                                                              "en": g[x["ip"]].get("country") or cc, "city": g[x["ip"]].get("city", ""),
                                                              "isp": g[x["ip"]].get("isp", "")})
        except Exception: pass
    keep.sort(key=lambda x: (x.get("fail", 0), x["ms"]))
    d["ips"], d["achecked"] = keep, int(time.time())
    if full: d["checked"] = int(time.time())
    if keep: _store(scope, d)
    else: clear(scope)
    after = [(x["ip"], x["port"], x.get("dom")) for x in keep[:d.get("per", 2)]]
    return before != after

def clear(scope):
    with STORE_LOCK:
        try: os.remove(_path(scope))
        except FileNotFoundError: pass

def summary(scope):
    d = load(scope)
    if not d: return {"count": 0}
    rows = []
    for x in d["ips"]:
        r = {"ip": x["ip"], "port": x["port"], "ms": x["ms"], "fail": x.get("fail", 0)}
        for k in KEEP: r[k] = x.get(k) or ""
        r["flag"] = flag(x.get("cc"))
        rows.append(r)
    return {"count": len(rows), "mode": d.get("mode"), "per": d.get("per"), "share": d.get("share"),
            "checked": max(d.get("checked", 0), d.get("achecked", 0)), "ips": rows}

def _retest_loop():
    time.sleep(90)
    while True:
        try:
            if _get_domain():
                for fn in os.listdir(DIR):
                    if not fn.endswith(".json") or fn == "geo.json": continue
                    scope = fn[:-5]; d = load(scope)
                    if not d: continue
                    full = time.time() - d.get("checked", 0) >= RETEST
                    if not full and time.time() - d.get("achecked", 0) < ACTIVE_RETEST: continue
                    changed = retest(scope, full)
                    if changed:
                        _log(f"clean IP {'owner list' if scope == 'global' else scope[:10]}: a dead IP was replaced")
                        if scope == "global":
                            try: _on_change()
                            except Exception as e: _log("clean IP apply:", e)
                    time.sleep(1)
        except Exception as e: _log("clean IP re-test:", e)
        time.sleep(60)

# ---------------- subscription token check ----------------
_VALID = {}

def valid_token(token):
    if not re.fullmatch(r"[A-Za-z0-9_\-.=%]{8,300}", token or ""): return False
    c = _VALID.get(token)
    if c and time.time() - c < 300: return True
    try:
        with urllib.request.urlopen(f"{BASE}/{SUB_PATH}/{urllib.parse.quote(token, safe='')}/info", timeout=10) as r:
            ok = r.status == 200
    except Exception: ok = False
    if ok: _VALID[token] = time.time()
    return ok

# ---------------- rewriting links ----------------
def _b64d(s):
    s = s.strip(); s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.replace("+", "-").replace("/", "_"))

def _host_fmt(ip): return f"[{ip}]" if ":" in ip else ip

def rewrite(link, ip, port, tag):
    """same config, but the phone connects to `ip`; SNI and Host stay the real domain"""
    try:
        if link.startswith("vmess://"):
            j = json.loads(_b64d(link[8:]).decode())
            dom = j.get("sni") or j.get("host") or j.get("add")
            j["sni"] = j.get("sni") or dom; j["host"] = j.get("host") or dom
            j["add"], j["port"] = ip, str(port)
            j["ps"] = f"{j.get('ps', '')} · {tag}"
            return "vmess://" + base64.b64encode(json.dumps(j, ensure_ascii=False, separators=(",", ":")).encode()).decode()
        m = re.match(r"^([a-z0-9+.-]+)://([^@/?#]*@)?(\[[^\]]+\]|[^:/?#]+)(?::(\d+))?([^?#]*)(\?[^#]*)?(#.*)?$", link, re.I)
        if not m: return None
        scheme, cred, host, _, path, query, frag = m.groups()
        if scheme.lower() not in ("vless", "trojan", "ss", "hysteria2", "hy2", "tuic"): return None
        host = host.strip("[]")
        qs = urllib.parse.parse_qsl((query or "?")[1:], keep_blank_values=True)
        keys = {k.lower() for k, _ in qs}
        if "sni" not in keys and "peer" not in keys: qs.append(("sni", host))
        if "host" not in keys and any(k.lower() == "type" and v.lower() in ("ws", "httpupgrade", "xhttp", "splithttp", "h2", "http") for k, v in qs):
            qs.append(("host", host))
        name = urllib.parse.unquote((frag or "#")[1:])
        return (f"{scheme}://{cred or ''}{_host_fmt(ip)}:{port}{path}?{urllib.parse.urlencode(qs, safe='/:,')}"
                f"#{urllib.parse.quote(name + ' · ' + tag)}")
    except Exception:
        return None

def _fetch(token, ua):
    """links of this user straight from the panel + the panel's subscription headers"""
    for kind in ("links", "links-base64", "v2ray", ""):
        url = f"{BASE}/{SUB_PATH}/{urllib.parse.quote(token, safe='')}" + (f"/{kind}" if kind else "")
        try:
            r = urllib.request.Request(url, headers={"User-Agent": ua or "v2rayNG/1.8", "Accept": "text/plain"})
            with urllib.request.urlopen(r, timeout=20) as resp:
                body = resp.read().decode(errors="ignore"); hdr = dict(resp.headers.items())
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) and kind == "": return None, {}
            continue
        except Exception: continue
        txt = body.strip()
        if txt and "://" not in txt[:200]:
            try: txt = _b64d(txt).decode(errors="ignore")
            except Exception: pass
        links = [l.strip() for l in txt.splitlines() if re.match(r"^[a-z][a-z0-9+.-]*://\S+$", l.strip(), re.I)]
        if links: return links, hdr
    return [], {}

def build_sub(token, ua=""):
    """(status, headers, body) for /sub/<token>/jx-ip"""
    if not valid_token(token): return 404, {}, b"not found"
    links, hdr = _fetch(token, ua)
    if links is None: return 404, {}, b"not found"
    d = load(scope_of(token))
    if not d or not d.get("ips"):
        g = load("global")
        d = g if g and g.get("share", True) and g.get("ips") else None
    out = []
    if d:
        ips = d["ips"][:d.get("per", 2)]
        for link in links:
            for n, x in enumerate(ips, 1):
                tag = " ".join(t for t in (flag(x.get("cc")), x.get("fa") or "", f"IP{n}") if t)
                r = rewrite(link, x["ip"], x["port"], tag)
                if r: out.append(r)
        if d.get("mode") != "ip" or not out: out += links
    else:
        out = links
    keep = {k: v for k, v in hdr.items() if k.lower() in ("subscription-userinfo", "profile-update-interval", "profile-title",
                                                          "support-url", "profile-web-page-url", "announce")}
    if "profile-title" not in {k.lower() for k in keep}: keep["profile-title"] = "base64:" + base64.b64encode("Super JinX · IP".encode()).decode()
    keep["Content-Type"] = "text/plain; charset=utf-8"
    keep["Cache-Control"] = "no-store"
    keep["Content-Disposition"] = 'attachment; filename="jinx-ip"'
    return 200, keep, base64.b64encode("\n".join(out).encode())
