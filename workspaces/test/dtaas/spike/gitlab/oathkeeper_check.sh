#!/bin/bash
# Spike S3: which introspection fields reach Oathkeeper's .Subject and
# .Extra, and whether the 30-second cache holds. Needs no GitLab.
set -euo pipefail

compose=(docker compose -f compose.yml --profile oathkeeper)
"${compose[@]}" up -d oathkeeper fake-relay >/dev/null
for _ in $(seq 60); do
  curl -fsS http://localhost:4456/health/ready >/dev/null 2>&1 && break
  sleep 1
done
sleep 5  # ready is reported before the access rules load

calls() {
  "${compose[@]}" exec -T fake-relay python3 -c \
    'import urllib.request; print(urllib.request.urlopen("http://localhost:8080/calls").read().decode())'
}

decide() {
  curl -s -o /dev/null -D - -b "dtaas_access_token=$1" \
    "http://localhost:4456/decisions/user1/lab" | tr -d '\r' \
    | grep -iE '^(HTTP|x-user|x-client)'
}

echo "== active token, first request"; decide good
echo "== active token, second request"; decide good
echo "== inactive token"; decide bad
echo "== fake relay saw"; calls
"${compose[@]}" stop oathkeeper fake-relay >/dev/null
"${compose[@]}" rm -f oathkeeper fake-relay >/dev/null
