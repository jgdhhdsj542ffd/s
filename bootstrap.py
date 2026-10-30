"""Super JinX bootstrap: zero-touch setup for PasarGuard on Railway. Idempotent: safe on every boot.
v6.3: works in every Railway region (domain is learned live, never skipped) + multi-location
(extra Railway services in other regions join this panel as nodes with one code)."""
import base64, hashlib, hmac, json, os, re, secrets, sys, time, urllib.error, urllib.parse, urllib.request
import subprocess

BASE = "http://127.0.0.1:8000"
DATA = os.getenv("JINX_DATA", "/var/lib/pasarguard")
RUN = os.getenv("JINX_RUN", "/run/jinx")
USER, PASS = "admin", "admin"          # first-boot login; change it later in the panel or with the owner key
RESELLER_USER, RESELLER_PASS, RESELLER_GB = "reseller", "reseller", 50
CORE_NAME, NODE_NAME = "JinX-Core", "JinX-Core"
# group names (old names are renamed in place, users and templates stay attached)
PRO_GROUP, STD_GROUP, IP_GROUP = "♛ JinX Royal", "◆ JinX Prime", "◈ JinX Phantom"
OLD_NAMES = {"pro": ("جینکس پرو",), "std": ("𝗝𝗶𝗻𝗫", "jinx-all"), "ip": ()}
TITLE = (os.getenv("CONFIG_TITLE") or "جینکس | 𝐒𝐮𝐩𝐞𝐫 𝐉𝐢𝐧𝐗").strip()   # shown after every config name
GB = 1024 ** 3
DAY = 86400

# All configs go through Railway's TLS edge on 443 with alpn=http/1.1 (the only thing Railway serves).
# ?ed=2560 = early data: the first packet rides on the handshake -> one round trip less per connection.
INBOUNDS = [
    # tag              proto     port  net            server path  fp         name            group
    ("JX-VLESS-WS-1", "vless",  10001, "ws",          "/ws/",     "chrome",  "𝗣𝗿𝗼",          "pro"),
    ("JX-VLESS-WS-2", "vless",  10002, "ws",          "/stream/", "firefox", "⚡ 𝗙𝗹𝗮𝘀𝗵",    "std"),
    ("JX-TROJAN-WS",  "trojan", 10003, "ws",          "/live/",   "safari",  "🔥 𝗙𝗶𝗿𝗲",     "std"),
    ("JX-VMESS-WS",   "vmess",  10004, "ws",          "/gw/",     "edge",    "💎 𝗗𝗶𝗮𝗺𝗼𝗻𝗱", "std"),
    ("JX-VLESS-HU",   "vless",  10005, "httpupgrade", "/cdn/",    "ios",     "🌙 𝗡𝗶𝗴𝗵𝘁",    "std"),
]
EARLY_DATA = "?ed=2560"
# "Shield" twins: the same config with the TLS hello cut in small pieces (fragment). It gets through on
# operators / cities where the plain one is slow or blocked (SNI filtering). Normal ones stay untouched.
SHIELD = {"JX-VLESS-WS-1": "🛡 𝗣𝗿𝗼 𝗦𝗵𝗶𝗲𝗹𝗱", "JX-VLESS-WS-2": "🛡 𝗦𝗵𝗶𝗲𝗹𝗱", "JX-VLESS-HU": "🛡 𝗦𝗵𝗶𝗲𝗹𝗱 𝗡𝗶𝗴𝗵𝘁"}
SHIELD_MARK = "🛡"
FRAGMENT = {"xray": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}}
# clean IP twins: the same 5 configs on their own inbounds, so they can live in their own group
IP_INBOUNDS = [(t + "-IP", pr, po + 10, n, pa, fp, nm, "ip") for (t, pr, po, n, pa, fp, nm, g) in INBOUNDS]
try:
    _P = json.load(open(f"{DATA}/paths.json"))
    INBOUNDS = [(t, pr, po, n, _P.get(t, pa), fp, nm, g) for (t, pr, po, n, pa, fp, nm, g) in INBOUNDS]
    IP_INBOUNDS = [(t, pr, po, n, _P[t], fp, nm, g) for (t, pr, po, n, pa, fp, nm, g) in IP_INBOUNDS if t in _P]
except Exception as _e:
    print("[bootstrap] paths.json missing, run genpaths.py first:", _e, flush=True); sys.exit(1)
TEMPLATES = [  # name, GB, days, groups, old name (renamed in place)
    ("◆ Prime · 10GB · 30 روز", 10, 30, ("std",), "10GB - 30 روز"),
    ("◆ Prime · 30GB · 30 روز", 30, 30, ("std",), "30GB - 30 روز"),
    ("◆ Prime · 50GB · 30 روز", 50, 30, ("std",), "50GB - 30 روز"),
    ("◆ Prime · 100GB · 30 روز", 100, 30, ("std",), "100GB - 30 روز"),
    ("◆ Prime · 200GB · 60 روز", 200, 60, ("std",), "200GB - 60 روز"),
    ("◆ Prime · نامحدود · 30 روز", 0, 30, ("std",), "نامحدود - 30 روز"),
    ("♛ Royal · 30GB · 30 روز", 30, 30, ("pro",), "Pro 30GB - 30 روز"),
    ("♛ Royal · 50GB · 30 روز", 50, 30, ("pro",), "Pro 50GB - 30 روز"),
    ("♛ Royal · 100GB · 30 روز", 100, 30, ("pro",), "Pro 100GB - 30 روز"),
    ("♛ Royal · نامحدود · 30 روز", 0, 30, ("pro",), "Pro نامحدود - 30 روز"),
    # only when the clean IP group exists: domain configs + clean IP configs together
    ("◈ Phantom · 50GB · 30 روز", 50, 30, ("std", "ip"), None),
    ("◈ Phantom · 100GB · 30 روز", 100, 30, ("std", "ip"), None),
    ("◈ Phantom · نامحدود · 30 روز", 0, 30, ("std", "ip"), None),
]
FIRST_USER = os.getenv("FIRST_USER", "jinx_user1")

TOKEN = None
CORE_ID = None
GIDS = {}         # group ids, shared by the watcher and the owner card

def log(*a): print("[bootstrap]", *a, flush=True)

# setup progress for the welcome page on the bare domain (GET /jinx/ready)
BOOT_T = time.time()
READY = {"panel": False, "core": False, "configs": False, "ready": False}
def _ready_once(): return os.path.exists(f"{os.getenv('JINX_DATA', '/var/lib/pasarguard')}/.setup_done")

# ---------------- domain: env first, otherwise learned live from real visits (works in every region) ----------------
DOMAIN_FILE = f"{DATA}/domain.txt"
HOST_LOG = f"{RUN}/host.log"
_DOM_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SKIP_HOSTS = ("healthcheck.railway.app", "localhost")

def _valid_domain(d):
    d = (d or "").strip().lower().rstrip(".")
    return d if _DOM_RE.match(d) and d not in _SKIP_HOSTS and not d.endswith(".railway.internal") else ""

def _learn_domain():
    """nginx writes the Host of every panel/sub visit to host.log; keep the newest public one."""
    try:
        if not os.path.exists(HOST_LOG) or os.path.getsize(HOST_LOG) == 0: return ""
        with open(HOST_LOG, "r+") as f:
            lines = f.read().split()
            f.seek(0); f.truncate()                      # keep the log tiny
        for h in reversed(lines):
            d = _valid_domain(h.split(":")[0])
            if d: return d
    except Exception as e: log("domain learn:", e)
    return ""

def get_domain():
    env = _valid_domain(os.getenv("PUBLIC_DOMAIN")) or _valid_domain(os.getenv("RAILWAY_PUBLIC_DOMAIN"))
    if env: return env
    learned = _learn_domain()
    saved = ""
    try: saved = _valid_domain(open(DOMAIN_FILE).read())
    except Exception: pass
    if learned and learned != saved:
        try: open(DOMAIN_FILE, "w").write(learned); log("domain learned from visits:", learned)
        except Exception: pass
        return learned
    return saved

# ---------------- locations (Railway regions) ----------------
REGIONS = [  # (match, flag, name)
    ("europe-west4", "🇳🇱", "هلند"), ("us-west", "🇺🇸", "آمریکا غرب"), ("us-east", "🇺🇸", "آمریکا شرق"),
    ("asia-southeast", "🇸🇬", "سنگاپور"), ("europe", "🇪🇺", "اروپا"), ("asia", "🌏", "آسیا"), ("us-", "🇺🇸", "آمریکا"),
]

def location(region, override=""):
    """(flag, name). JINX_LOCATION like '🇩🇪 آلمان' wins over the auto detected region."""
    o = (override or "").strip()
    if o:
        parts = o.split(None, 1)
        if len(parts) == 2 and not parts[0].isalnum(): return parts[0], parts[1]
        return "🌐", o
    r = (region or "").lower()
    for key, flag, name in REGIONS:
        if key in r: return flag, name
    return "🌐", "سرور"

MY_LOC = location(os.getenv("RAILWAY_REPLICA_REGION"), os.getenv("JINX_LOCATION"))

_GLOBAL = object()

def req(method, path, body=None, form=False, ok=(200, 201, 204), token=_GLOBAL):
    url = BASE + path
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    tok = TOKEN if token is _GLOBAL else token
    if tok: headers["Authorization"] = f"Bearer {tok}"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            try: return resp.status, json.loads(raw) if raw.strip() else None
            except ValueError: return resp.status, raw
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="ignore")
        try: return e.code, json.loads(txt)
        except Exception: return e.code, txt

def must(method, path, body=None):
    code, res = req(method, path, body)
    if code == 401:
        login(); code, res = req(method, path, body)
    if code not in (200, 201, 204):
        raise RuntimeError(f"{method} {path} -> {code}: {res}")
    return res

def as_list(res, key):
    if isinstance(res, list): return res
    if isinstance(res, dict): return res.get(key) or []
    return []

def wait_panel():
    for _ in range(180):
        try:
            code, _ = req("GET", "/api/system")
            if code in (200, 401, 403): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError("panel did not come up")

TEMP_KEY_PY = """
import asyncio
from app.db.base import GetDB
from app.db.crud.temp_key import create_temp_key
async def main():
    async with GetDB() as db:
        k = await create_temp_key(db)
        print("KEY=" + k.key)
asyncio.run(main())
"""

def temp_key():
    out = subprocess.run([sys.executable, "-c", TEMP_KEY_PY], cwd="/code", capture_output=True, text=True, timeout=60)
    for line in out.stdout.splitlines():
        if line.startswith("KEY="): return line[4:].strip()
    raise RuntimeError(f"temp key failed: {out.stderr[-500:]}")

ADMIN_PW_PY = """
import asyncio, sys
from app.db.base import GetDB
from app.db.crud.admin import get_owner, get_admin
from app.models.admin import _hash_password_sync
async def main():
    mode, user, pw = sys.argv[1], sys.argv[2], sys.argv[3]
    async with GetDB() as db:
        if mode == "owner":
            o = await get_owner(db)
        else:
            o = await get_admin(db, user, load_users=False, load_usage_logs=False)
        if o is None:
            print("MISSING"); return
        o.username = user
        o.hashed_password = _hash_password_sync(pw)
        await db.commit()
        print("OK")
asyncio.run(main())
"""

def write_password(mode, user, pw):
    out = subprocess.run([sys.executable, "-c", ADMIN_PW_PY, mode, user, pw], cwd="/code",
                         capture_output=True, text=True, timeout=90)
    ok = out.stdout.strip().splitlines()[-1:] == ["OK"]
    if not ok: log(f"password write ({mode} {user}) failed:", (out.stdout + out.stderr)[-400:])
    return ok

def strong_tmp():
    return "Jx" + secrets.token_hex(8) + "Aa9!Zz7"

TOKEN_PY = """
import asyncio
from app.db.base import GetDB
from app.db.crud.admin import get_owner
from app.utils.jwt import create_admin_token
async def main():
    async with GetDB() as db:
        o = await get_owner(db)
        if o is None:
            print("NOOWNER"); return
        print("TOKEN=" + await create_admin_token(o.id, o.username))
asyncio.run(main())
"""

def owner_token():
    out = subprocess.run([sys.executable, "-c", TOKEN_PY], cwd="/code", capture_output=True, text=True, timeout=60)
    for line in out.stdout.splitlines():
        if line.startswith("TOKEN="): return line[6:].strip()
        if line.strip() == "NOOWNER": return None
    raise RuntimeError(f"token failed: {(out.stdout + out.stderr)[-400:]}")

MARKER = f"{DATA}/.owner_initialized"
RESELLER_MARKER = f"{DATA}/.reseller_initialized"

def ensure_owner():
    """First boot: owner = admin/admin. After that the password is YOURS: change it in the panel
    or with the owner key (API Keys page). Bootstrap never touches it again."""
    if owner_token() is None:
        code, res = req("POST", "/api/setup/owner", {"key": temp_key(), "username": "jinxowner", "password": strong_tmp()}, token=None)
        if code not in (200, 201, 409): log(f"owner create failed {code}: {res}")
        if os.path.exists(MARKER): os.remove(MARKER)
    if not os.path.exists(MARKER):
        if write_password("owner", USER, PASS):
            open(MARKER, "w").write(str(int(time.time())))
            log("owner ready:", USER, "/", PASS, "(first boot)")

def print_owner_key():
    try:
        k = temp_key()
        log("=" * 60)
        log("OWNER KEY (valid 5 min, one use):", k)
        log("use it on the login page (Owner access) to set a new password")
        log("need a new key? Restart the service in Railway")
        log("=" * 60)
    except Exception as e:
        log("owner key failed:", e)

def login():
    global TOKEN
    ensure_owner()
    for _ in range(30):
        tok = owner_token()
        if tok:
            TOKEN = tok; return
        time.sleep(3)
    raise RuntimeError("could not get an owner token")

def inbound(tag, proto, port, net, path):
    stream = {"network": net, "security": "none"}
    if net == "ws": stream["wsSettings"] = {"path": path, "heartbeatPeriod": 30}   # keeps mobile connections alive
    elif net == "httpupgrade": stream["httpupgradeSettings"] = {"path": path}
    elif net == "xhttp": stream["xhttpSettings"] = {"path": path, "mode": "auto"}
    settings = {"clients": []}
    if proto == "vless": settings["decryption"] = "none"
    return {"tag": tag, "listen": "127.0.0.1", "port": port, "protocol": proto,
            "settings": settings, "streamSettings": stream,
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True}}

# speed-test addresses that apps use for "ping" (real delay). They are answered right here on the server
# (local nginx, port 8099) instead of going out to Google/Cloudflare, so the delay shown is only phone <-> server.
PING_DOMAINS = ["full:www.gstatic.com", "full:connectivitycheck.gstatic.com", "full:www.google.com",
                "full:clients3.google.com", "full:connectivitycheck.android.com", "full:cp.cloudflare.com"]

CORE_CONFIG = {
    "log": {"loglevel": "warning"},
    # plain UDP DNS (no TLS handshake on the first lookup), IPv4 only, answers are cached by the core
    "dns": {"servers": ["1.1.1.1", "8.8.8.8", "localhost"], "queryStrategy": "UseIPv4"},
    "inbounds": [inbound(*i[:5]) for i in INBOUNDS + IP_INBOUNDS],
    "outbounds": [
        {"protocol": "freedom", "tag": "DIRECT", "settings": {"domainStrategy": "UseIPv4"}},
        {"protocol": "blackhole", "tag": "BLOCK"},
        {"protocol": "freedom", "tag": "PING", "settings": {"redirect": "127.0.0.1:8099"}},
    ],
    # AsIs: no extra DNS lookup per connection just to check the rules (faster first byte)
    "routing": {"domainStrategy": "AsIs", "rules": [
        {"type": "field", "domain": PING_DOMAINS, "port": "80", "outboundTag": "PING"},
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "BLOCK"},
        {"type": "field", "protocol": ["bittorrent"], "outboundTag": "BLOCK"},
        # QUIC (UDP 443) is slow inside a WebSocket tunnel: blocking it makes YouTube/Instagram/browsers
        # switch to normal TCP right away, which is much faster here
        {"type": "field", "network": "udp", "port": "443", "outboundTag": "BLOCK"},
    ]},
    # patient on weak mobile networks, but closes dead connections so memory stays free
    "policy": {"levels": {"0": {"handshake": 8, "connIdle": 300, "uplinkOnly": 2, "downlinkOnly": 5, "bufferSize": 512}}},
}

def ensure_core():
    cores = as_list(must("GET", "/api/cores"), "cores")
    for c in cores:
        if c.get("name") in (CORE_NAME, "jinx-core"):
            if c.get("name") == CORE_NAME and c.get("config") == CORE_CONFIG:
                log("core ok (unchanged)", c["id"]); return c["id"]
            body = {"name": CORE_NAME, "config": CORE_CONFIG, "exclude_inbound_tags": [], "fallbacks_inbound_tags": []}
            code, res = req("PUT", f"/api/core/{c['id']}?restart_nodes=true", body)
            if code not in (200, 201):  # node may still be starting: save config without restart
                code, res = req("PUT", f"/api/core/{c['id']}?restart_nodes=false", body)
            log("core updated" if code in (200, 201) else f"core update failed {code}: {res}", c["id"])
            return c["id"]
    c = must("POST", "/api/core", {"name": CORE_NAME, "config": CORE_CONFIG,
                                    "exclude_inbound_tags": [], "fallbacks_inbound_tags": []})
    log("core created", c["id"]); return c["id"]

def _node_body(name, address, port, core_id):
    return {"name": name, "address": address, "port": int(port), "usage_coefficient": 1,
            "connection_type": "grpc", "server_ca": open(f"{DATA}/node-certs/cert.pem").read().strip(),
            "keep_alive": 60, "core_config_id": core_id, "api_key": open(f"{DATA}/node_api_key").read().strip()}

def _upsert_node(name, body, aliases=()):
    for n in as_list(must("GET", "/api/nodes"), "nodes"):
        if n.get("name") in (name,) + tuple(aliases):
            same = all(n.get(k) == body[k] for k in ("name", "address", "port", "core_config_id"))
            if not same or n.get("server_ca", body["server_ca"]) != body["server_ca"]:
                must("PUT", f"/api/node/{n['id']}", body); return "updated"
            return "ok"
    must("POST", "/api/node", body); return "created"

def ensure_node(core_id):
    log("node", _upsert_node(NODE_NAME, _node_body(NODE_NAME, "127.0.0.1", 62050, core_id), ("jinx-local",)))

def clean_ip_on():
    try:
        import cleanip
        g = cleanip.load("global") or {}
        return bool(g.get("ips")) and bool(IP_INBOUNDS)
    except Exception: return False

def ensure_groups():
    """♛ Royal -> the Pro config, ◆ Prime -> the other 4, ◈ Phantom -> the 5 clean IP twins (created by itself
    as soon as the owner saves a clean IP list). Old names are renamed in place, so users never lose a group."""
    want = {"pro": (PRO_GROUP, [i[0] for i in INBOUNDS if i[7] == "pro"]),
            "std": (STD_GROUP, [i[0] for i in INBOUNDS if i[7] == "std"])}
    groups = as_list(must("GET", "/api/groups"), "groups")
    by_name = {g.get("name"): g for g in groups}
    if IP_GROUP in by_name or clean_ip_on():
        want["ip"] = (IP_GROUP, [i[0] for i in IP_INBOUNDS])
    ids = {}
    for key, (name, tags) in want.items():
        g = by_name.get(name)
        if not g:
            for old in OLD_NAMES.get(key, ()):
                if old in by_name: g = by_name[old]; break
        if g:
            if g.get("name") != name or sorted(g.get("inbound_tags") or []) != sorted(tags):
                must("PUT", f"/api/group/{g['id']}", {"name": name, "inbound_tags": tags})
                log("group ready:", name if g.get("name") == name else f"{g.get('name')} -> {name}")
            ids[key] = g["id"]
        else:
            if not tags: continue
            g = must("POST", "/api/group", {"name": name, "inbound_tags": tags}); ids[key] = g["id"]
            log("group created:", name, f"({len(tags)} config)")
    return ids

# ---------------- extra locations (other Railway regions running this repo with JINX_MODE=node) ----------------
NODES_FILE = f"{DATA}/locations.json"
SECRET_FILE = f"{DATA}/node_join_secret"
STALE = 3 * DAY       # a location that has not checked in for 3 days is hidden from subscriptions

def join_secret():
    if not os.path.exists(SECRET_FILE):
        open(SECRET_FILE, "w").write(secrets.token_urlsafe(24))
    return open(SECRET_FILE).read().strip()

def load_locations():
    try:
        with open(NODES_FILE, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception: return {}

def save_locations(d):
    tmp = NODES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, NODES_FILE)

def node_code():
    """one string that turns a new Railway service in any region into a location of this panel"""
    dom = get_domain()
    if not dom: raise ValueError("اول برای پنل دامنه بساز (Generate Domain)")
    payload = {"v": 1, "panel": dom, "secret": join_secret(),
               "api_key": open(f"{DATA}/node_api_key").read().strip(),
               "cert": open(f"{DATA}/node-certs/cert.pem").read().strip(),
               "key": open(f"{DATA}/node-certs/key.pem").read().strip(),
               "paths": json.load(open(f"{DATA}/paths.json"))}
    return "JX1." + base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")

def node_name(nid):
    return "JinX-Loc-" + hashlib.sha1(nid.encode()).hexdigest()[:6]

def ensure_locations():
    if not CORE_ID: return
    locs = load_locations(); now = time.time()
    for nid, n in locs.items():
        if now - n.get("last", 0) > STALE: continue
        try:
            st = _upsert_node(node_name(nid), _node_body(node_name(nid), n["tcp_host"], n["tcp_port"], CORE_ID))
            if st != "ok": log(f"location {n.get('flag','')} {n.get('loc','')} node {st}")
        except Exception as e: log("location node:", e)

QUIET = {}

def _norm(v):
    """compare host fields the same way whether the API returns a string, a list or an enum"""
    if isinstance(v, list): return [str(x).lower() for x in v]
    if v is None: return None
    if isinstance(v, bool): return v
    return [str(v).lower()] if isinstance(v, str) and "," not in v else str(v).lower()

def _addr(h):
    a = h.get("address")
    if isinstance(a, list): a = a[0] if a else ""
    return str(a or "").lower()

SHIELD_OFF = {}   # set when this panel version does not accept fragment settings: then only normal configs

def _differs(cur, want):
    """dicts (fragment settings): only the keys we set count, extra keys the panel adds are fine"""
    if isinstance(want, dict):
        if not isinstance(cur, dict): return True
        return any(_differs(cur.get(k), v) for k, v in want.items())
    return _norm(cur) != _norm(want)

def _is_shield(h):
    return SHIELD_MARK in str(h.get("remark") or "")

def _put_shield(existing, tag, d, body):
    """create/update one Shield host; if the panel refuses the fragment field, switch Shield off (no errors, no loop)"""
    mine = [h for h in existing if h.get("inbound_tag") == tag and _addr(h) == d and _is_shield(h)]
    for extra in mine[1:]: req("DELETE", f"/api/host/{extra['id']}")
    if mine:
        cur = mine[0]
        if not any(_differs(cur.get(k), v) for k, v in body.items()): return 0
        code, res = req("PUT", f"/api/host/{cur['id']}", {**body, "id": cur["id"]})
    else:
        code, res = req("POST", "/api/host/", body)
    if code in (200, 201): return 1
    if code not in (400, 422): return 0          # panel busy / restarting: try again next round
    SHIELD_OFF["v"] = True
    log("Shield configs skipped: this panel version does not take fragment settings", code)
    if mine: req("DELETE", f"/api/host/{mine[0]['id']}")
    return 0

def ensure_hosts():
    """one host per config per location. Never skipped forever: as soon as a domain is known, configs appear."""
    dom = get_domain()
    places = []                                    # (domain, flag, name, enabled)
    if dom: places.append((dom, MY_LOC[0], MY_LOC[1], True))
    now = time.time()
    for nid, n in sorted(load_locations().items(), key=lambda x: x[1].get("added", 0)):
        d = _valid_domain(n.get("domain"))
        if d and d != dom: places.append((d, n.get("flag", "🌐"), n.get("loc", "سرور"), now - n.get("last", 0) <= STALE))
    if not places:
        if not QUIET.get("nodom"):
            log("WAITING for a domain: Settings > Networking > Generate Domain (port 8080), or just open the panel once")
            QUIET["nodom"] = True
        return
    QUIET["nodom"] = False
    multi = len(places) > 1
    existing = as_list(must("GET", "/api/hosts"), "hosts")
    wanted, changed, prio = set(), 0, 0
    for li, (d, flag, loc, on) in enumerate(places):
        for idx, (tag, proto, port, net, path, fp, name, grp) in enumerate(INBOUNDS):
            prio += 1
            wanted.add((tag, d))
            remark = f"{flag} {name} · {loc} | {TITLE}" if multi or flag != "🌐" else f"{name} | {TITLE}"
            body = {"remark": remark, "allowinsecure": False, "address": [d], "inbound_tag": tag,
                    "port": 443, "sni": [d], "host": [d], "path": path + EARLY_DATA, "security": "tls",
                    "alpn": ["http/1.1"], "fingerprint": fp, "priority": prio, "is_disabled": not on}
            mine = [h for h in existing if h.get("inbound_tag") == tag and _addr(h) == d and not _is_shield(h)]
            if mine:
                cur = mine[0]
                if any(_norm(cur.get(k)) != _norm(v) for k, v in body.items()):
                    must("PUT", f"/api/host/{cur['id']}", {**body, "id": cur["id"]}); changed += 1
                for extra in mine[1:]:
                    req("DELETE", f"/api/host/{extra['id']}")
            else:
                must("POST", "/api/host/", body); changed += 1
        for tag, proto, port, net, path, fp, name, grp in INBOUNDS:   # Shield twins (fragment), after the normal ones
            if tag not in SHIELD or SHIELD_OFF.get("v"): continue
            prio += 1
            sname = SHIELD[tag]
            remark = f"{flag} {sname} · {loc} | {TITLE}" if multi or flag != "🌐" else f"{sname} | {TITLE}"
            body = {"remark": remark, "allowinsecure": False, "address": [d], "inbound_tag": tag,
                    "port": 443, "sni": [d], "host": [d], "path": path + EARLY_DATA, "security": "tls",
                    "alpn": ["http/1.1"], "fingerprint": "chrome", "priority": prio, "is_disabled": not on,
                    "fragment_settings": FRAGMENT}
            changed += _put_shield(existing, tag, d, body)
    # clean IP group: the 5 twins, one host per IP (address = IP, SNI/Host = panel domain)
    try:
        import cleanip
        g = cleanip.load("global") or {}
    except Exception: g = {}
    if dom and g.get("ips") and IP_INBOUNDS:
        per = max(1, min(10, int(g.get("per") or 2)))
        alive = {p[0] for p in places}
        for n, x in enumerate(g["ips"][:per], 1):
            use = x.get("dom") if x.get("dom") in alive else dom          # IP in a country where we have a location -> that location
            fl = cleanip.flag(x.get("cc")); cname = x.get("fa") or ""
            for idx, (tag, proto, port, net, path, fp, name, grp) in enumerate(IP_INBOUNDS):
                prio += 1
                wanted.add((tag, x["ip"].lower()))
                remark = f"{fl + ' ' if fl else ''}◈ {name}{' · ' + cname if cname else ''} · IP{n} | {TITLE}"
                body = {"remark": remark, "allowinsecure": False, "address": [x["ip"]], "inbound_tag": tag,
                        "port": int(x["port"]), "sni": [use], "host": [use], "path": path + EARLY_DATA, "security": "tls",
                        "alpn": ["http/1.1"], "fingerprint": fp, "priority": prio, "is_disabled": False}
                mine = [h for h in existing if h.get("inbound_tag") == tag and _addr(h) == x["ip"].lower()]
                if mine:
                    if any(_norm(mine[0].get(k)) != _norm(v) for k, v in body.items()):
                        must("PUT", f"/api/host/{mine[0]['id']}", {**body, "id": mine[0]["id"]}); changed += 1
                    for extra in mine[1:]: req("DELETE", f"/api/host/{extra['id']}")
                else:
                    must("POST", "/api/host/", body); changed += 1
    for h in existing:   # hosts of old domains / removed locations / auto-created ones: our tags only
        if str(h.get("inbound_tag") or "").startswith("JX-") and ((h.get("inbound_tag"), _addr(h)) not in wanted
                or (_is_shield(h) and (SHIELD_OFF.get("v") or h.get("inbound_tag") not in SHIELD))):
            req("DELETE", f"/api/host/{h['id']}"); changed += 1
    if changed or not QUIET.get("hosts"):
        log(f"{(len(INBOUNDS) + (0 if SHIELD_OFF.get('v') else len(SHIELD))) * len(places)} configs ready in {len(places)} location(s):", ", ".join(p[0] for p in places))
        QUIET["hosts"] = True
    if dom and QUIET.get("settings_for") != dom:
        ensure_settings(dom)

def ensure_settings(dom=None):
    dom = dom or get_domain()
    if not dom: return
    code, s = req("GET", "/api/settings")
    if code != 200 or not isinstance(s, dict) or "subscription" not in s:
        log("settings endpoint not as expected, skipped"); return
    sub = s["subscription"]
    want = {"url_prefix": f"https://{dom}", "profile_title": TITLE, "update_interval": 12}
    if all(sub.get(k) == v for k, v in want.items()):
        QUIET["settings_for"] = dom; return
    sub.update(want)
    code, res = req("PUT", "/api/settings", {"subscription": sub})
    if code in (200, 201): QUIET["settings_for"] = dom
    log("subscription settings", "ok" if code in (200, 201) else f"skipped ({code})")

RESELLER_ROLE = "نماینده"

def ensure_reseller_role(gids):
    """Reseller role: manages only its own users, must use the ready-made templates."""
    own = {"scope": 1}
    role = {
        "name": RESELLER_ROLE,
        "permissions": {
            "users": {"create": own, "read": own, "read_simple": own, "update": own, "delete": own,
                      "reset_usage": own, "revoke_sub": own, "activate_next_plan": own},
            "templates": {"read": True, "read_simple": True},
            "groups": {"read_simple": True},
            "system": {"read": True},
            "settings": {"read_general": True},
        },
        "access": {"require_template": True, "allowed_group_ids": sorted(gids.values())},
        "disabled_when_limited": True,
    }
    base = "/api/admin-role"
    code, res = req("GET", base + "s")
    if code != 200: log("reseller role endpoint not found, skipped"); return
    mine = [r for r in as_list(res, "roles") if r.get("name") == RESELLER_ROLE]
    if mine:
        acc = mine[0].get("access") or {}
        if sorted(acc.get("allowed_group_ids") or []) != role["access"]["allowed_group_ids"] \
                or acc.get("require_template") is not True:
            req("PUT", f"{base}/{mine[0]['id']}", {"access": role["access"]})
        log("reseller role ready"); return
    code, res = req("POST", base, role)
    log("reseller role created" if code in (200, 201) else f"reseller role failed {code}: {res}")

def role_id_by_name(name):
    code, res = req("GET", "/api/admin-roles")
    for r in as_list(res, "roles") if code == 200 else []:
        if r.get("name") == name: return r["id"]
    return None

def ensure_demo_reseller():
    """A ready reseller account (like the reseller panels): 50 GB quota, own users only."""
    if os.getenv("DEMO_RESELLER", "on").lower() in ("off", "false", "0", "no"):
        return
    if os.path.exists(RESELLER_MARKER): return      # created once; deleting it in the panel is respected
    rid = role_id_by_name(RESELLER_ROLE)
    if not rid: log("demo reseller skipped (no role)"); return
    code, _ = req("POST", "/api/admin/token", {"username": RESELLER_USER, "password": RESELLER_PASS}, form=True, token=None)
    if code == 200: open(RESELLER_MARKER, "w").write("1"); return
    code, res = req("POST", "/api/admin", {"username": RESELLER_USER, "password": strong_tmp(),
                                           "role_id": rid, "data_limit": RESELLER_GB * GB,
                                           "profile_title": TITLE})
    if code in (200, 201):
        if write_password("user", RESELLER_USER, RESELLER_PASS):
            open(RESELLER_MARKER, "w").write("1"); log("demo reseller ready:", RESELLER_USER)
    elif code == 409:
        open(RESELLER_MARKER, "w").write("1")   # already exists with its own password
    else:
        log(f"demo reseller failed {code}: {res}")

def ensure_templates(gids):
    have = {t.get("name"): t for t in as_list(must("GET", "/api/user_templates"), "templates")}
    for name, gb, days, grps, old in TEMPLATES:
        if any(g not in gids for g in grps): continue          # Phantom templates wait for the clean IP group
        gid = [gids[g] for g in grps]
        body = {"name": name, "data_limit": gb * GB, "expire_duration": days * DAY, "group_ids": gid,
                "status": "active", "data_limit_reset_strategy": "no_reset"}
        cur = have.get(name) or (have.get(old) if old else None)
        if cur:
            if cur.get("name") != name or sorted(cur.get("group_ids") or []) != sorted(gid):
                req("PUT", f"/api/user_template/{cur['id']}", body)
        else:
            must("POST", "/api/user_template", body)
    log("user templates ready")

def remove_demo_user():
    """Users list starts EMPTY. Removes the old auto-created test user from earlier versions (only that one)."""
    code, u = req("GET", f"/api/user/{FIRST_USER}")
    if code == 200 and isinstance(u, dict) and (u.get("note") or "") == "auto-created":
        c, _ = req("DELETE", f"/api/user/{FIRST_USER}")
        log("removed old test user", FIRST_USER) if c in (200, 204) else log(f"could not remove {FIRST_USER}: {c}")

def attach_orphans(gids):
    """Users created in the panel without a group get the 4 configs automatically."""
    code, res = req("GET", "/api/users?no_group=true&limit=200")
    if code == 401:
        login(); code, res = req("GET", "/api/users?no_group=true&limit=200")
    if code != 200: return
    for u in as_list(res, "users"):
        if u.get("group_ids"): continue
        c, r = req("PUT", f"/api/user/{u['username']}", {"group_ids": [gids["std"]]})
        log(f"no group picked for {u['username']} -> {STD_GROUP}" if c == 200 else f"attach {u['username']} failed {c}: {r}")

def heal_node(state):
    """Self-healing: if a core (local or a location) is not connected twice in a row, reconnect it."""
    code, res = req("GET", "/api/nodes")
    if code == 401: login(); code, res = req("GET", "/api/nodes")
    if code != 200: return
    for n in as_list(res, "nodes"):
        name = n.get("name") or ""
        if name != NODE_NAME and not name.startswith("JinX-Loc-"): continue
        st = str(n.get("status") or "")
        if st in ("connected", "disabled"):
            state[name] = 0; continue
        state[name] = state.get(name, 0) + 1
        if state[name] >= 2:
            log(f"{name} status '{st}' -> auto-reconnect")
            c, _ = req("POST", f"/api/node/{n['id']}/reconnect")
            if c not in (200, 204):
                if name == NODE_NAME:
                    c, _ = req("POST", f"/api/core/{n.get('core_config_id')}/restart")
                if c not in (200, 204):   # re-saving the node makes the panel connect again
                    try:
                        if name == NODE_NAME: body = _node_body(NODE_NAME, "127.0.0.1", 62050, n.get("core_config_id"))
                        else: body = _node_body(name, n.get("address"), n.get("port"), n.get("core_config_id"))
                        must("PUT", f"/api/node/{n['id']}", body)
                    except Exception as e: log("node reconnect failed:", e)
            state[name] = 0

def ip_places():
    """other live locations for the clean IP matcher: [(domain, country code, flag, name)]"""
    out, now, dom = [], time.time(), get_domain()
    for nid, n in load_locations().items():
        d = _valid_domain(n.get("domain"))
        if d and d != dom and now - n.get("last", 0) <= STALE:
            out.append((d, cleanip.cc_of_flag(n.get("flag")), n.get("flag", ""), n.get("loc", "")))
    return out

def apply_clean_ip():
    """owner saved / removed the clean IP list: group, templates, reseller access and hosts follow right away"""
    with SETUP_LOCK:
      try:
        new = ensure_groups()
        fresh = set(new) - set(GIDS); GIDS.update(new)
        if fresh: ensure_templates(GIDS); ensure_reseller_role(GIDS)
        ensure_hosts()
      except Exception as e: log("clean IP apply:", e)

def watch(gids):
    log("watcher on: auto-attach users, self-heal cores, live domain, locations, settings")
    state, i = {}, 0
    def regroup():
        new = ensure_groups()
        if new:
            fresh = set(new) - set(gids)
            gids.update(new)
            if fresh:     # the clean IP group just appeared: templates + reseller access follow
                step("templates", ensure_templates, gids); step("reseller role", ensure_reseller_role, gids)
    while True:
        for job, every in ((lambda: attach_orphans(gids), 1), (ensure_locations, 2), (ensure_hosts, 2),
                           (lambda: heal_node(state), 4), (regroup, 4), (tune_db, 240)):
            if i % every == 0:
                try:
                    with SETUP_LOCK: job()
                except Exception as e: log("self-heal:", e)
        i += 1
        time.sleep(15)

# ---------------- owner key service (used by the golden owner card on the "API Keys" page) ----------------
# POST /jinx/key        -> 5-minute one-use key              {key, ttl, recent}
# POST /jinx/password   -> change owner password directly    {ok, recent}
# POST /jinx/history    -> last owner-access events          {recent}
# POST /jinx/locations  -> locations + join code (owner)     {code, here, locations}
# POST /jinx/node-join  -> called by location services (secret, no owner login)
# POST /jinx/ip/{get,test,job,save,clear} -> clean IP lists (token = personal, owner = for everyone)
# GET  /jinx-sub/<token> -> /sub/<token>/jx-ip : the subscription with clean IP configs
# auth: the panel login token (Bearer) or {"username","password"} of the owner
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
SETUP_LOCK = threading.RLock()   # watcher and "owner saved IPs" never build groups / configs at the same time
_attempts = {}
_HIST_LOCK = threading.Lock()
_LOC_LOCK = threading.Lock()
HIST_FILE = f"{DATA}/owner_access.json"

def _history():
    try:
        with open(HIST_FILE, encoding="utf-8") as f: return json.load(f)[-8:]
    except Exception: return []

def _remember(kind, ip, by):
    with _HIST_LOCK:
        h = _history() + [{"t": int(time.time()), "kind": kind, "ip": ip, "by": by}]
        try:
            with open(HIST_FILE + ".tmp", "w", encoding="utf-8") as f: f.write(json.dumps(h[-8:], ensure_ascii=False))
            os.replace(HIST_FILE + ".tmp", HIST_FILE)
        except Exception as e: log("history save failed:", e)
        return h[-8:]

def _client_ip(h, fallback):
    # chain = [what the phone sent..., real phone IP (added by Railway's edge), edge IP (added by our nginx)]
    # the entry before the last one cannot be faked by the phone, so limits cannot be dodged with a fake header
    xff = [x.strip() for x in (h.get("X-Forwarded-For") or "").split(",") if x.strip()]
    real = xff[-2] if len(xff) >= 2 else (xff[0] if xff else "")
    return (real or h.get("X-Real-IP") or fallback or "?")[:45]

def _fa(n): return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def _hide_ip(ip):
    if ":" in ip: return ip.split(":")[0] + ":…"
    p = ip.split("."); return ".".join(p[:2] + ["*", "*"]) if len(p) == 4 else ip

def _node_status():
    code, res = req("GET", "/api/nodes")
    return {n.get("name"): str(n.get("status") or "") for n in as_list(res, "nodes")} if code == 200 else {}

class KeyHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/jinx-sub/"):
            token = urllib.parse.unquote(path[len("/jinx-sub/"):].strip("/"))
            try: code, hdr, body = cleanip.build_sub(token, self.headers.get("User-Agent", ""))
            except Exception as e: log("clean IP sub:", e); code, hdr, body = 502, {}, b"try again"
            self.send_response(code)
            for k, v in hdr.items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path == "/jinx/ready":
            r = dict(READY); r["configs"] = bool(r["configs"] or get_domain())
            if _ready_once() and r["panel"]: r["ready"] = True     # set up before: usable as soon as the panel answers
            r["since"] = int(time.time() - BOOT_T); self._send(200, r); return
        self._send(405, {"detail": "use POST"})

    def _ip(self, path, body, ip):
        """clean IP: personal list (auth = subscription token) or the owner's list for everyone"""
        act = path.rsplit("/", 1)[-1]
        token = str(body.get("token") or "")
        if token:
            if not cleanip.valid_token(token): return self._send(404, {"detail": "لینک اشتراک معتبر نیست"})
            scope = cleanip.scope_of(token)
        else:
            me, bad = self._owner(body, ip)
            if bad: return self._send(bad[0], {"detail": bad[1], **bad[2]})
            scope = "global"
        if act == "get":
            g = cleanip.load("global") or {}
            out = {"mine": cleanip.summary(scope), "domain": get_domain(), "group": IP_GROUP, "title": TITLE,
                   "sample": INBOUNDS[0][6] if INBOUNDS else "Pro", "places": [{"flag": p[2], "loc": p[3], "cc": p[1]} for p in ip_places()],
                   "global": len(g.get("ips") or []) if (scope == "global" or g.get("share", True)) else 0}
            return self._send(200, out)
        if act == "test":
            now = time.time(); hist = [t for t in _attempts.get("ip" + ip, []) if now - t < 600]
            if len(hist) >= 8: return self._send(429, {"detail": "زیاد تست گرفتی، چند دقیقه صبر کن"})
            hist.append(now); _attempts["ip" + ip] = hist
            jid, err = cleanip.start_job(scope, str(body.get("text") or ""))
            if err: return self._send(400, {"detail": err})
            return self._send(200, {"job": jid, "total": cleanip.JOBS[jid]["total"]})
        if act == "job":
            st = cleanip.job_status(scope, str(body.get("job") or ""))
            return self._send(200, st) if st else self._send(404, {"detail": "تست پیدا نشد، دوباره فایل رو بده"})
        if act == "save":
            # only IPs this server really tested OK (latest test of this list, or already in the list) can be saved
            ok = {}
            for j in list(cleanip.JOBS.values()):
                if j["scope"] == scope and j["done"]:
                    for x in j["results"]: ok[(x["ip"], int(x["port"]))] = x
            for x in (cleanip.load(scope) or {}).get("ips", []): ok.setdefault((x["ip"], int(x["port"])), x)
            want = []
            for x in body.get("ips") or []:
                try: k = (str(x.get("ip")), int(x.get("port") or 443))
                except Exception: continue
                if k in ok and ok[k] not in want: want.append(ok[k])
            if not want: return self._send(400, {"detail": "اول آی‌پی‌ها رو تست کن، فقط آی‌پی‌های سالم ذخیره میشن"})
            d = cleanip.save(scope, want, str(body.get("mode") or "both"), body.get("per") or 2,
                             body.get("share") if scope == "global" else None)
            log(f"clean IP list saved ({'owner, for everyone' if scope == 'global' else 'personal'}): {len(d['ips'])} IPs")
            if scope == "global": threading.Thread(target=apply_clean_ip, daemon=True).start()
            return self._send(200, {"ok": True, "mine": cleanip.summary(scope), "group": IP_GROUP if scope == "global" else None})
        if act == "remove":
            try: m = cleanip.remove_one(scope, str(body.get("ip") or ""), int(body.get("port") or 443))
            except Exception: return self._send(400, {"detail": "آی‌پی درست نیست"})
            if scope == "global": threading.Thread(target=apply_clean_ip, daemon=True).start()
            return self._send(200, {"ok": True, "mine": m})
        if act == "retest":
            now = time.time(); hist = [t for t in _attempts.get("rt" + ip, []) if now - t < 300]
            if len(hist) >= 6: return self._send(429, {"detail": "چند دقیقه صبر کن و دوباره بررسی کن"})
            hist.append(now); _attempts["rt" + ip] = hist
            changed = cleanip.retest(scope, True)
            if changed and scope == "global": threading.Thread(target=apply_clean_ip, daemon=True).start()
            return self._send(200, {"ok": True, "changed": changed, "mine": cleanip.summary(scope)})
        if act == "clear":
            cleanip.clear(scope)
            if scope == "global": threading.Thread(target=apply_clean_ip, daemon=True).start()
            return self._send(200, {"ok": True, "mine": {"count": 0}})
        return self._send(404, {"detail": "not found"})

    def _owner(self, body, ip):
        """returns (owner_dict, None) or (None, (code, message, extra))"""
        now = time.time(); hist = [t for t in _attempts.get(ip, []) if now - t < 600]; _attempts[ip] = hist
        allf = [t for t in _attempts.get("*", []) if now - t < 600]; _attempts["*"] = allf
        if len(allf) >= 40 and not (self.headers.get("Authorization", "").lower().startswith("bearer ") and not body.get("username")):
            return None, (429, "تلاش اشتباه زیاد بود، ۱۰ دقیقه دیگه امتحان کن", {"wait_min": 10})   # many IPs guessing together
        if len(hist) >= 5:
            wait = int(600 - (now - hist[0])) // 60 + 1
            return None, (429, f"تلاش زیاد بود، {_fa(wait)} دقیقه دیگه امتحان کن", {"wait_min": wait})
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer ") and not body.get("username"):
            token = auth[7:].strip()                     # already logged in to the panel
        else:
            u, p = str(body.get("username", ""))[:64], str(body.get("password", ""))[:128]
            if not u or not p: return None, (401, "یوزر و رمز مالک رو وارد کن", {"need_login": True})
            code, res = req_anon("POST", "/api/admin/token", {"username": u, "password": p}, form=True)
            if code != 200:
                hist.append(now); allf.append(now)
                left = max(0, 5 - len(hist))
                return None, (401, "یوزر یا رمز اشتباهه" + (f" ({_fa(left)} تلاش دیگه)" if left else ""), {"left": left, "need_login": True})
            token = res["access_token"]
        code, me = req_anon("GET", "/api/admin", token=token)
        if code != 200: return None, (401, "دوباره وارد پنل شو", {"need_login": True})
        if not ((me or {}).get("role") or {}).get("is_owner"):
            return None, (403, "فقط مالک پنل به این بخش دسترسی داره", {})
        return me, None

    def _join(self, body, ip):
        """a location service checks in (every minute). Auth: the secret inside the join code."""
        now = time.time(); hist = [t for t in _attempts.get("j" + ip, []) if now - t < 600]; _attempts["j" + ip] = hist
        if len(hist) >= 10: return self._send(429, {"detail": "too many tries"})
        if not hmac.compare_digest(str(body.get("secret", "")), join_secret()):
            hist.append(now); return self._send(403, {"detail": "wrong code"})
        nid = re.sub(r"[^A-Za-z0-9_.-]", "", str(body.get("id", "")))[:64]
        dom = _valid_domain(body.get("domain"))
        th = _valid_domain(body.get("tcp_host"))
        try: tp = int(body.get("tcp_port"))
        except Exception: tp = 0
        if not nid or not dom or not th or not (0 < tp < 65536):
            return self._send(400, {"detail": "domain (8080) and TCP proxy (62050) are both needed"})
        flag, loc = location(str(body.get("region", ""))[:64], str(body.get("loc", ""))[:40])
        with _LOC_LOCK:
            locs = load_locations(); old = locs.get(nid, {})
            locs[nid] = {"domain": dom, "tcp_host": th, "tcp_port": tp, "flag": flag, "loc": loc,
                         "region": str(body.get("region", ""))[:64], "added": old.get("added", int(now)), "last": int(now)}
            save_locations(locs)
        if not old: log(f"new location joined: {flag} {loc} ({dom})")
        return self._send(200, {"ok": True, "name": f"{flag} {loc}"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        is_ip = path.startswith("/jinx/ip/")
        if not is_ip and path not in ("/jinx/key", "/jinx/password", "/jinx/history", "/jinx/locations", "/jinx/node-join"):
            return self._send(404, {"detail": "not found"})
        try: body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 700000 if is_ip else 8192)) or b"{}") or {}
        except Exception: body = {}
        if not isinstance(body, dict): body = {}
        ip = _client_ip(self.headers, self.client_address[0])
        if path == "/jinx/node-join": return self._join(body, ip)
        if is_ip: return self._ip(path, body, ip)
        me, bad = self._owner(body, ip)
        if bad: return self._send(bad[0], {"detail": bad[1], **bad[2]})
        who = me.get("username") or "owner"
        pub = lambda h: [{"t": x["t"], "kind": x["kind"], "ip": _hide_ip(x.get("ip", "?")), "by": x.get("by")} for x in h]

        if path == "/jinx/history":
            return self._send(200, {"recent": pub(_history())})

        if path == "/jinx/locations":
            if body.get("remove"):
                with _LOC_LOCK:
                    locs = load_locations(); gone = locs.pop(str(body["remove"]), None); save_locations(locs)
                if gone:
                    try:
                        for n in as_list(must("GET", "/api/nodes"), "nodes"):
                            if n.get("name") == node_name(str(body["remove"])): req("DELETE", f"/api/node/{n['id']}")
                    except Exception as e: log("location node remove:", e)
                    log("location removed:", gone.get("domain"))
            try: code = node_code()
            except Exception as e: code = ""; log("join code:", e)
            st = _node_status(); now = time.time()
            out = [{"id": nid, "flag": n.get("flag"), "loc": n.get("loc"), "domain": n.get("domain"),
                    "last": n.get("last"), "stale": now - n.get("last", 0) > STALE,
                    "status": st.get(node_name(nid), "")} for nid, n in load_locations().items()]
            return self._send(200, {"code": code, "here": {"flag": MY_LOC[0], "loc": MY_LOC[1], "domain": get_domain(),
                                    "status": st.get(NODE_NAME, "")}, "locations": out})

        if path == "/jinx/password":
            new = str(body.get("new_password", ""))
            if len(new) < 8 or new.isdigit() or new.isalpha():
                return self._send(400, {"detail": "رمز جدید حداقل ۸ کاراکتر و ترکیب حرف و عدد باشه"})
            if len(new) > 128 or any(ord(c) < 33 for c in new):
                return self._send(400, {"detail": "رمز نباید فاصله یا کاراکتر عجیب داشته باشه"})
            # write it, then prove it: log in to the panel with the new password before saying "done"
            ok = False
            for _ in range(2):
                if write_password("owner", who, new) and _login_works(who, new): ok = True; break
                time.sleep(1)
            if not ok:
                return self._send(500, {"detail": "تغییر رمز تأیید نشد، دوباره امتحان کن"})
            log("owner password changed (verified by a real login) for", who)
            return self._send(200, {"ok": True, "verified": True, "username": who, "recent": pub(_remember("password", ip, who))})

        try: key = temp_key()
        except Exception as e:
            log("owner key failed:", e); return self._send(500, {"detail": "ساخت کلید ممکن نشد، چند ثانیه دیگه دوباره بزن"})
        log("owner key issued from API Keys page for", who)
        self._send(200, {"key": key, "ttl": 300, "issued": int(time.time()), "recent": pub(_remember("key", ip, who))})

def _login_works(user, pw):
    """the panel's own login: 200 means the new password really works"""
    try:
        code, res = req_anon("POST", "/api/admin/token", {"username": user, "password": pw}, form=True)
        return code == 200 and bool((res or {}).get("access_token"))
    except Exception as e:
        log("password check:", e); return False

def req_anon(method, path, body=None, form=False, token=None):
    return req(method, path, body, form=form, token=token)  # thread-safe: never touches the global token

import cleanip

def start_key_service():
    cleanip.init(get_domain, log, get_places=ip_places, on_change=lambda: threading.Thread(target=apply_clean_ip, daemon=True).start())
    srv = ThreadingHTTPServer(("127.0.0.1", 8100), KeyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("owner tools ready: Advanced > Owner security / Locations / Clean IP")

def tune_db():
    """WAL mode: the panel can read while it writes (many users at once, no 'database is locked')"""
    import sqlite3
    db = f"{DATA}/db.sqlite3"
    if not os.path.exists(db): return
    try:
        con = sqlite3.connect(db, timeout=30)
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        if mode.lower() != "wal":
            con.execute("PRAGMA journal_mode=WAL"); log("database: WAL mode on")
        con.execute("PRAGMA wal_checkpoint(PASSIVE)")
        con.close()
    except Exception as e: log("database tune:", e)

def step(name, fn, *a):
    try: return fn(*a)
    except Exception as e: log(f"{name} failed: {e}")

def main():
    global CORE_ID
    log(f"this service runs in: {MY_LOC[0]} {MY_LOC[1]} ({os.getenv('RAILWAY_REPLICA_REGION') or 'region unknown'})")
    wait_panel(); login(); print_owner_key()
    READY["panel"] = True
    step("key service", start_key_service)
    CORE_ID = ensure_core()
    time.sleep(2)
    step("node", ensure_node, CORE_ID)
    READY["core"] = True
    gid = None
    for _ in range(20):  # inbounds appear after the core is saved (slower regions need longer)
        gid = step("groups", ensure_groups)
        if gid: break
        time.sleep(3)
    if not gid: raise RuntimeError("groups could not be created")
    GIDS.update(gid); gid = GIDS
    step("database", tune_db)
    step("locations", ensure_locations)
    step("hosts", ensure_hosts)
    step("templates", ensure_templates, gid)
    step("reseller role", ensure_reseller_role, gid)
    step("demo reseller", ensure_demo_reseller)
    step("clean users", remove_demo_user)
    dom = get_domain()
    READY["configs"] = bool(dom); READY["ready"] = True
    try: open(f"{DATA}/.setup_done", "w").write(str(int(time.time())))
    except Exception: pass
    log("DONE ->", f"https://{dom}/dashboard/" if dom else "generate a Railway domain (port 8080), configs appear by themselves")
    watch(gid)

if __name__ == "__main__":
    try: main()
    except Exception as e: log("FATAL", e); sys.exit(1)
