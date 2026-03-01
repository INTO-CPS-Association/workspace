#!/usr/bin/env bash
# Automates the OAuth2 / OIDC login flow against a local Dex provider for
# headless CI testing with traefik-forward-auth.
#
# Usage:
#   ci_auth_login.sh [BASE_URL] [USERNAME] [DEX_BASE_URL] [PASSWORD] [CURL_OPTS]
#
# Defaults:
#   BASE_URL     = http://localhost
#   USERNAME     = user1
#   DEX_BASE_URL = http://dex:5556
#   PASSWORD     = password
#   CURL_OPTS    = (empty)  — pass "-k" here for self-signed TLS certificates
#
# Exit codes:
#   0 – login succeeded and protected resource returned HTTP 200
#   1 – any failure
#
# How it works (no browser needed):
#   1. GET <BASE_URL>/<USERNAME>/
#      -> traefik-forward-auth issues 302 to Dex /dex/auth?...
#      -> curl follows all redirects and lands on Dex's login page HTML
#   2. Extract the form <action> URL from the Dex login page.
#   3. POST username + password to that URL.
#      -> Dex validates credentials, skips the approval screen, and issues
#         a 302 to <BASE_URL>/_oauth?code=XXX&state=XXX
#      -> curl follows the redirect; traefik-forward-auth exchanges the code,
#         validates the token, sets the _forward_auth cookie, and issues a
#         final 302 back to the original protected URL.
#   4. GET <BASE_URL>/<USERNAME>/ with the session cookie -> expect HTTP 200.

set -euo pipefail

BASE_URL="${1:-http://localhost}"
USERNAME="${2:-user1}"
DEX_BASE_URL="${3:-http://dex:5556}"
PASSWORD="${4:-password}"
# Extra curl flags, e.g. "-k" to bypass self-signed certificate validation
CURL_OPTS="${5:-}"
EMAIL="${USERNAME}@localhost"

COOKIE_JAR="$(mktemp /tmp/dex_cookies.XXXXXX)"
LOGIN_HTML="$(mktemp /tmp/dex_login.XXXXXX.html)"
AFTER_LOGIN_HTML="$(mktemp /tmp/dex_after_login.XXXXXX.html)"

cleanup() {
    rm -f "${COOKIE_JAR}" "${LOGIN_HTML}" "${AFTER_LOGIN_HTML}"
}
trap cleanup EXIT

PROTECTED_URL="${BASE_URL}/${USERNAME}/"

echo "=== Step 1: Follow redirects to Dex login page ==="
# shellcheck disable=SC2086
curl --silent \
    --location \
    ${CURL_OPTS} \
    --cookie-jar "${COOKIE_JAR}" \
    --cookie "${COOKIE_JAR}" \
    --output "${LOGIN_HTML}" \
    "${PROTECTED_URL}"

if ! grep -q 'action=' "${LOGIN_HTML}"; then
    echo "❌ Did not reach Dex login page. HTML dump:"
    cat "${LOGIN_HTML}"
    exit 1
fi

echo "=== Step 2: Extract Dex login form action URL ==="
# Dex renders: <form method="post" action="/dex/auth/local?req=XXXXX">
FORM_PATH="$(grep -oP '(?<=action=")[^"]+' "${LOGIN_HTML}" | head -1)"

if [[ -z "${FORM_PATH}" ]]; then
    echo "❌ Could not extract form action from Dex login page."
    cat "${LOGIN_HTML}"
    exit 1
fi

echo "  Form action path: ${FORM_PATH}"

echo "=== Step 3: POST credentials to Dex, follow redirects ==="
# After a successful login Dex redirects to /_oauth which traefik-forward-auth
# handles.  The -L flag makes curl follow all redirects automatically so we end
# up back at the protected URL and the _forward_auth cookie gets stored.
# shellcheck disable=SC2086
HTTP_CODE="$(curl --silent \
    --location \
    ${CURL_OPTS} \
    --cookie-jar "${COOKIE_JAR}" \
    --cookie "${COOKIE_JAR}" \
    --request POST \
    --data-urlencode "login=${EMAIL}" \
    --data-urlencode "password=${PASSWORD}" \
    --output "${AFTER_LOGIN_HTML}" \
    --write-out "%{http_code}" \
    "${DEX_BASE_URL}${FORM_PATH}")"

echo "  HTTP code after credential POST + redirect chain: ${HTTP_CODE}"

echo "=== Step 4: Access protected resource with session cookie ==="
# shellcheck disable=SC2086
AUTH_CODE="$(curl --silent \
    ${CURL_OPTS} \
    --cookie-jar "${COOKIE_JAR}" \
    --cookie "${COOKIE_JAR}" \
    --output /dev/null \
    --write-out "%{http_code}" \
    "${PROTECTED_URL}")"

echo "  HTTP code for authenticated request: ${AUTH_CODE}"

if [[ "${AUTH_CODE}" == "200" ]]; then
    echo "✅ Authenticated access to ${PROTECTED_URL} succeeded (HTTP 200)"
    exit 0
else
    echo "❌ Expected HTTP 200 but got ${AUTH_CODE}"
    echo "--- Dex login page ---"
    cat "${LOGIN_HTML}"
    echo "--- Response after login POST ---"
    cat "${AFTER_LOGIN_HTML}"
    exit 1
fi
