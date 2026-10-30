#!/usr/bin/env bash
# Super JinX health check: nginx edge must answer; in panel mode the panel API too.
curl -fsS -o /dev/null --max-time 4 http://127.0.0.1:8080/healthz || exit 1
[ "${JINX_MODE:-panel}" = "node" ] && exit 0
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:8000/api/system)
[ "$code" = "200" ] || [ "$code" = "401" ] || exit 1
exit 0
