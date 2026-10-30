"""Super JinX location mode (JINX_MODE=node): this Railway service becomes an extra location of your panel.
setup -> unpack JINX_CODE (from the panel: API Keys > Locations) and write the node files + nginx config
join  -> check in with the panel every minute, so the panel adds this location to every subscription."""
import base64, json, os, sys, time, urllib.error, urllib.request

DATA = os.getenv("JINX_DATA", "/var/lib/pasarguard")
PORT = int(os.getenv("PORT", "8080"))

def log(*a): print("[location]", *a, flush=True)

def code():
    raw = (os.getenv("JINX_CODE") or "").strip()
    if not raw.startswith("JX1."):
        log("JINX_CODE is missing or wrong. Copy it from the panel: API Keys > Locations > Copy code"); sys.exit(1)
    b = raw[4:]
    try: return json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    except Exception as e: log("JINX_CODE could not be read (copy it again, completely):", e); sys.exit(1)

NGINX = """user www-data;
worker_processes auto;
worker_rlimit_nofile 65535;
pid /run/nginx.pid;
events { worker_connections 16384; multi_accept on; }
http {
  access_log off;
  error_log /dev/stdout warn;
  sendfile on; tcp_nodelay on; keepalive_timeout 75s;
  # ---- fast "ping": speed-test requests of the apps are answered here (the core sends them to 8099) ----
  server {
    listen 127.0.0.1:8099 default_server;
    location = /generate_204 { return 204; }
    location / { return 301 https://$host$request_uri; }
  }
  server {
    listen 127.0.0.1:8099;
    server_name cp.cloudflare.com;
    location / { return 204; }
  }
  server {
    listen __PORT__ default_server;
    #__EXTRA_LISTEN__
    location = /healthz { return 200 "ok"; }
    include __DATA__/inbounds.inc;
    location / { return 404; }
  }
}
"""

def setup():
    c = code()
    os.makedirs(f"{DATA}/node-certs", exist_ok=True)
    open(f"{DATA}/node_api_key", "w").write(c["api_key"].strip() + "\n")
    open(f"{DATA}/node-certs/cert.pem", "w").write(c["cert"].strip() + "\n")
    open(f"{DATA}/node-certs/key.pem", "w").write(c["key"].strip() + "\n")
    os.chmod(f"{DATA}/node-certs/key.pem", 0o600)
    json.dump(c["paths"], open(f"{DATA}/paths.json", "w"), indent=1)
    rp = os.getenv("JINX_RPORT", "")
    extra = f"listen {rp};" if rp.isdigit() and 0 < int(rp) < 65536 and int(rp) != PORT and int(rp) not in (8000, 8099, 8100, 8101, 62050) and not 10001 <= int(rp) <= 10099 else ""
    open("/etc/nginx/nginx.conf", "w").write(NGINX.replace("__PORT__", str(PORT)).replace("#__EXTRA_LISTEN__", extra).replace("__DATA__", DATA))
    log("ready for panel", c["panel"])

def env_domain():
    return (os.getenv("PUBLIC_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().lower()

def join():
    c = code()
    url = f"https://{c['panel']}/jinx/node-join"
    nid = os.getenv("RAILWAY_SERVICE_ID") or env_domain() or "location"
    hinted, joined = 0, False
    while True:
        dom, th, tp = env_domain(), os.getenv("RAILWAY_TCP_PROXY_DOMAIN", ""), os.getenv("RAILWAY_TCP_PROXY_PORT", "")
        if not dom or not th or not tp:
            if time.time() - hinted > 600:
                miss = [x for x, ok in (("Generate Domain روی پورت 8080", dom), ("TCP Proxy روی پورت 62050", th and tp)) if not ok]
                log("still needed in Railway > Settings > Networking:", " + ".join(miss), "(then redeploy)")
                hinted = time.time()
            time.sleep(30); continue
        body = json.dumps({"secret": c["secret"], "id": nid, "domain": dom, "tcp_host": th, "tcp_port": tp,
                           "region": os.getenv("RAILWAY_REPLICA_REGION", ""), "loc": os.getenv("JINX_LOCATION", "")}).encode()
        try:
            r = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": "jinx-location"})
            with urllib.request.urlopen(r, timeout=20) as resp:
                res = json.loads(resp.read() or b"{}")
                if not joined: log("joined the panel as", res.get("name", "?"), "| configs show up in subscriptions within a minute"); joined = True
        except urllib.error.HTTPError as e:
            joined = False
            log("panel said", e.code, "(403 = old code: copy a fresh one from the panel)" if e.code == 403 else "")
        except Exception as e:
            joined = False; log("panel not reachable yet:", e)
        time.sleep(60)

if __name__ == "__main__":
    {"setup": setup, "join": join}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: log("use: setup | join"))()
