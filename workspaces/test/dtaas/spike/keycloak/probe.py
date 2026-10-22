"""Spike S4: checks the Keycloak behaviour the storage design relies on.

Runs against the Keycloak of compose.yml after setup.py. The browser
steps (login, consent) run in headless Chromium against the public
address; the server-side calls (token, introspect, revoke) run inside
the `inside` container against http://keycloak:8080/auth, as
workspace-admin and login-relay would. Prints one line per check and
writes redacted responses to recorded/. Needs requests, pyjwt and
playwright. Run with: python3 -I probe.py
"""

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PUBLIC = "http://localhost:8180/auth"
INTERNAL = "http://keycloak:8080/auth"
HERE = Path(__file__).resolve().parent
STATE = json.loads(Path(os.environ.get("STATE", HERE / "state.json")).read_text(encoding="utf-8"))
RECORDED = HERE / "recorded"
SHOTS = RECORDED / "raw"
BACKUP_REDIRECT = "https://dtaas.example.org/login-relay/oauth/keycloak/callback"
LOGIN_REDIRECT = "https://dtaas.example.org/login-relay/callback"
OIDC = "protocol/openid-connect"
TOKEN_KEYS = ("access_token", "refresh_token", "id_token")
CHROMIUM = os.environ.get("CHROMIUM", str(next(Path.home().glob(
    ".cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"),
    "")))

results: list[tuple[str, bool, str]] = []

# Runs inside the `inside` container: one HTTP call, JSON in and out.
INSIDE_SCRIPT = r"""
import base64, json, sys, urllib.error, urllib.parse, urllib.request
req = json.load(sys.stdin)
data = urllib.parse.urlencode(req["data"]).encode() if req.get("data") is not None else None
r = urllib.request.Request(req["url"], data=data, method=req["method"])
for k, v in req.get("headers", {}).items():
    r.add_header(k, v)
if req.get("basic"):
    r.add_header("Authorization", "Basic " + base64.b64encode(req["basic"].encode()).decode())
try:
    with urllib.request.urlopen(r, timeout=20) as resp:
        status, body = resp.status, resp.read().decode()
except urllib.error.HTTPError as err:
    status, body = err.code, err.read().decode()
print(json.dumps({"status": status, "body": body}))
"""


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Records and prints one check."""
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    return ok


def note(name: str, detail: str) -> None:
    """Prints an observation that is not pass or fail."""
    print(f"NOTE  {name}  {detail}", flush=True)


def redact(value):
    """Replaces secrets in a provider response with placeholders."""
    if isinstance(value, dict):
        return {k: (f"<{k}>" if k in TOKEN_KEYS and isinstance(v, str)
                    else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def record(name: str, status: int, body) -> None:
    """Saves a redacted response for contract tests."""
    RECORDED.mkdir(exist_ok=True)
    (RECORDED / f"{name}.json").write_text(
        json.dumps({"status": status, "body": redact(body)}, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")


def inside(method: str, url: str, data: dict | None = None,
           basic: str | None = None, headers: dict | None = None) -> tuple[int, dict]:
    """Makes one HTTP call from inside the compose network."""
    proc = subprocess.run(
        ["docker", "compose", "-f", str(HERE / "compose.yml"), "exec", "-T",
         "inside", "python3", "-c", INSIDE_SCRIPT],
        input=json.dumps({"method": method, "url": url, "data": data,
                          "basic": basic, "headers": headers or {}}),
        capture_output=True, text=True, timeout=60, check=True)
    out = json.loads(proc.stdout)
    try:
        body = json.loads(out["body"]) if out["body"] else {}
    except json.JSONDecodeError:
        body = {"text": out["body"][:200]}
    return out["status"], body


def claims(token: str) -> dict:
    """Unverified JWT claims (the token came straight from Keycloak)."""
    return jwt.decode(token, options={"verify_signature": False})


def pkce_pair() -> tuple[str, str]:
    """Returns an RFC 7636 verifier and its S256 challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class BrowserUser:  # pylint: disable=too-few-public-methods
    """One user's headless Chromium context.

    Navigations away from Keycloak are answered with a stub page and
    recorded, so the redirect is captured without a DTaaS deployment.
    """

    def __init__(self, browser, username: str, realm: str = "dtaas"):
        self.username, self.realm = username, realm
        self.context = browser.new_context()
        self.page = self.context.new_page()
        self.captured: str | None = None
        # A route alone misses the redirect after a form post, so the
        # request event records the address and the route stubs the page.
        self.context.on("request", self._seen)
        self.context.route(re.compile(r"^https?://(?!localhost:8180/).*"),
                           self._capture)

    def _seen(self, request) -> None:
        if (request.is_navigation_request() and self.captured is None
                and not request.url.startswith("http://localhost:8180/")):
            self.captured = request.url

    def _capture(self, route) -> None:
        if route.request.is_navigation_request() and self.captured is None:
            self.captured = route.request.url
        route.fulfill(status=200, content_type="text/html", body="stub")

    def authorize(self, params: dict, shot: str = "") -> dict:
        """Opens the authorize URL, logs in and consents when asked."""
        self.captured = None
        # A fresh page per request, so a stubbed or failed redirect from
        # the previous one cannot interrupt this navigation.
        self.page.close()
        self.page = page = self.context.new_page()
        try:
            reply = page.goto(f"{PUBLIC}/realms/{self.realm}/{OIDC}/auth?"
                              f"{urlencode(params)}")
        except PlaywrightError:
            # An immediate redirect to the unresolvable DTaaS address
            # fails the navigation after the request event recorded it.
            if self.captured is None:
                raise
            reply = None
        login = consent = False
        if self.captured is None and page.locator("#username").count():
            login = True
            page.fill("#username", self.username)
            page.fill("#password", STATE["password"])
            page.click("#kc-login")
            page.wait_for_load_state("networkidle")
        if self.captured is None and page.locator("#kc-login[name=accept], "
                                                  "input[name=accept]").count():
            consent = True
            if shot:
                SHOTS.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(SHOTS / f"{shot}.png"))
            page.locator("#kc-login[name=accept], input[name=accept]").first.click()
            page.wait_for_load_state("networkidle")
        return {"login": login, "consent": consent,
                "status": reply.status if reply else 0,
                "location": self.captured,
                "text": page.inner_text("body")[:200] if self.captured is None else ""}


def query(location: str | None) -> dict:
    """Query parameters of a captured redirect."""
    return {k: v[0] for k, v in parse_qs(urlparse(location or "").query).items()}


def backup_params(challenge: str | None, **extra) -> dict:
    """Authorize parameters for the public workspace-backup client."""
    params = {"client_id": "workspace-backup", "redirect_uri": BACKUP_REDIRECT,
              "response_type": "code", "scope": "openid offline_access",
              "state": "user1." + secrets.token_urlsafe(8)}
    if challenge:
        params.update(code_challenge=challenge, code_challenge_method="S256")
    params.update(extra)
    return params


def token_url(realm: str = "dtaas") -> str:
    """Internal token endpoint."""
    return f"{INTERNAL}/realms/{realm}/{OIDC}/token"


def redeem(code: str, verifier: str | None, realm: str = "dtaas",
           redirect: str = BACKUP_REDIRECT) -> tuple[int, dict]:
    """Redeems a workspace-backup code as a public client, internally."""
    data = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect, "client_id": "workspace-backup"}
    if verifier is not None:
        data["code_verifier"] = verifier
    return inside("POST", token_url(realm), data)


def refresh(refresh_token: str, realm: str = "dtaas") -> tuple[int, dict]:
    """Refreshes as workspace-backup, internally."""
    return inside("POST", token_url(realm), {
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": "workspace-backup"})


def introspect(token: str, realm: str = "dtaas") -> tuple[int, dict]:
    """Introspects as login-relay's confidential client, internally."""
    return inside("POST", f"{token_url(realm)}/introspect", {"token": token},
                  basic=f"dtaas-workspace:{STATE['login_secret']}")


def connect(user: BrowserUser, shot: str = "") -> tuple[dict, dict]:
    """Full workspace-backup connect; returns (authorize, token reply)."""
    verifier, challenge = pkce_pair()
    auth = user.authorize(backup_params(challenge), shot=shot)
    status, body = redeem(query(auth["location"]).get("code", ""), verifier,
                          realm=user.realm)
    if status != 200:
        raise RuntimeError(f"connect failed: {status} {body}")
    return auth, body


def admin_headers() -> dict:
    """Bearer header for the master realm admin."""
    reply = requests.post(f"{PUBLIC}/realms/master/{OIDC}/token", timeout=30, data={
        "grant_type": "password", "client_id": "admin-cli",
        "username": "admin", "password": "Spike-admin-pw-2026!"})
    return {"Authorization": f"Bearer {reply.json()['access_token']}"}


def admin(method: str, path: str, **kwargs) -> requests.Response:
    """Admin REST call."""
    return requests.request(method, f"{PUBLIC}/admin{path}", timeout=30,
                            headers=admin_headers(), **kwargs)


def main() -> int:
    """Runs every check in one headless Chromium; 1 when any fails."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROMIUM, headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"])
        try:
            return run(browser)
        finally:
            browser.close()


def run(browser) -> int:  # pylint: disable=too-many-locals,too-many-statements
    """The checks."""
    server = requests.get(f"{PUBLIC}/admin/serverinfo", headers=admin_headers(),
                          timeout=30).json()
    note("keycloak_version", server.get("systemInfo", {}).get("version", "?"))

    # --- KC_HOSTNAME_BACKCHANNEL_DYNAMIC --------------------------------
    public = requests.get(f"{PUBLIC}/realms/dtaas/.well-known/openid-configuration",
                          timeout=30).json()
    _, internal = inside("GET", f"{INTERNAL}/realms/dtaas/.well-known/"
                         "openid-configuration")
    record("openid_configuration_internal", 200, internal)
    issuer = f"{PUBLIC}/realms/dtaas"
    check("issuer_public_from_both", public["issuer"] == internal["issuer"] == issuer,
          f"public={public['issuer']} internal={internal['issuer']}")
    check("authorize_endpoint_public_from_inside",
          internal["authorization_endpoint"].startswith(PUBLIC),
          internal["authorization_endpoint"])
    for key in ("token_endpoint", "introspection_endpoint", "jwks_uri",
                "userinfo_endpoint"):
        check(f"{key}_internal_from_inside", internal[key].startswith(INTERNAL),
              internal[key])
        check(f"{key}_public_from_host", public[key].startswith(PUBLIC), public[key])
    # Not backchannel in Keycloak's view: these stay public from inside.
    for key in ("revocation_endpoint", "end_session_endpoint"):
        note(f"{key}_from_inside", internal.get(key, ""))

    # --- workspace-backup: PKCE, consent, offline -----------------------
    user1 = BrowserUser(browser, "user1")
    verifier, challenge = pkce_pair()
    first = user1.authorize(backup_params(challenge), shot="consent-first")
    q = query(first["location"])
    check("authorize_returns_code", "code" in q,
          f"login={first['login']} consent={first['consent']} "
          f"location={(first['location'] or '')[:80]} text={first['text'][:80]}")
    check("consent_shown_first_time", first["consent"])
    check("state_returned_unchanged", q.get("state", "").startswith("user1."))
    note("redirect_has_iss_param", repr(q.get("iss")))
    status, body = redeem(q.get("code", ""), verifier)
    record("backup_token_authorization_code", status, body)
    check("public_redeem_with_verifier_no_secret", status == 200,
          f"status={status} keys={sorted(body)}")
    access, refresh1 = body["access_token"], body["refresh_token"]
    at, rt = claims(access), claims(refresh1)
    record("backup_access_token_claims", 200, at)
    record("backup_refresh_token_claims", 200, rt)
    check("refresh_token_is_offline", rt.get("typ") == "Offline", f"typ={rt.get('typ')}")
    check("scope_has_offline_access", "offline_access" in body.get("scope", ""),
          f"scope={body.get('scope')!r}")
    check("access_token_expires_in_300", body.get("expires_in") == 300,
          f"expires_in={body.get('expires_in')}")
    check("access_token_iss_public", at.get("iss") == issuer, f"iss={at.get('iss')}")
    check("access_token_azp_workspace_backup", at.get("azp") == "workspace-backup")
    check("owner_check_preferred_username", at.get("preferred_username") == "user1")
    check("access_token_aud_has_login_client", "dtaas-workspace" in
          (at.get("aud") if isinstance(at.get("aud"), list) else [at.get("aud")]),
          f"aud={at.get('aud')!r}")
    note("refresh_expires_in_offline", f"{body.get('refresh_expires_in')} "
         f"(refresh exp-iat={rt.get('exp', 0) - rt.get('iat', 0) if rt.get('exp') else None})")
    check("code_single_use", redeem(q.get("code", ""), verifier)[0] == 400)

    again = user1.authorize(backup_params(pkce_pair()[1]))
    # Keycloak does not keep a browser session that only an offline
    # request created, so this asks for the password again.
    note("consent_second_connect", f"login={again['login']} consent={again['consent']}")

    for label, use_verifier in (("no_verifier", None), ("wrong_verifier", "x" * 43)):
        _, chal = pkce_pair()
        auth = user1.authorize(backup_params(chal))
        status, body = redeem(query(auth["location"]).get("code", ""), use_verifier)
        record(f"backup_redeem_{label}", status, body)
        check(f"public_redeem_{label}_refused", status == 400, f"{status} {body}")
    auth = user1.authorize(backup_params(None))
    check("authorize_without_challenge_refused", "code" not in query(auth["location"]),
          f"location={(auth['location'] or '')[:120]} text={auth['text'][:80]}")
    _, chal = pkce_pair()
    auth = user1.authorize(backup_params(chal, code_challenge_method="plain"))
    check("authorize_plain_method_refused", "code" not in query(auth["location"]),
          f"location={(auth['location'] or '')[:120]}")

    variants = {
        "trailing_slash": BACKUP_REDIRECT + "/",
        "extra_query": BACKUP_REDIRECT + "?x=1",
        "sub_path": BACKUP_REDIRECT + "/x",
        "http_scheme": BACKUP_REDIRECT.replace("https:", "http:"),
        "other_host": BACKUP_REDIRECT.replace("dtaas.example.org", "evil.example.org"),
        "login_callback": LOGIN_REDIRECT,
    }
    for label, uri in variants.items():
        auth = user1.authorize(backup_params(pkce_pair()[1], redirect_uri=uri))
        check(f"redirect_refused_{label}", "code" not in query(auth["location"]),
              f"location={(auth['location'] or '')[:80]} text={auth['text'][:60]!r}")

    # --- Refresh: rotation, ID token ------------------------------------
    status, body = refresh(refresh1)
    record("backup_token_refresh", status, body)
    check("public_refresh_no_secret", status == 200, f"status={status}")
    refresh2 = body.get("refresh_token")
    note("refresh_returns_new_refresh_token", str(bool(refresh2) and refresh2 != refresh1))
    note("id_token_on_refresh", str("id_token" in body))
    check("refreshed_token_still_offline", claims(refresh2).get("typ") == "Offline")
    status, _ = refresh(refresh1)
    note("old_refresh_after_refresh_default_realm", f"status={status} "
         "(revokeRefreshToken off by default)")

    # --- Introspection by login-relay's confidential client -------------
    status, body = refresh(refresh2)
    access = body["access_token"]
    status, ibody = introspect(access)
    record("introspect_backup_token_by_login_client", status, ibody)
    check("login_client_introspects_backup_token",
          status == 200 and ibody.get("active") is True,
          f"status={status} keys={sorted(ibody)}")
    check("introspect_username", ibody.get("username") == "user1",
          f"username={ibody.get('username')!r}")
    check("introspect_client_id_backup", ibody.get("client_id") == "workspace-backup",
          f"client_id={ibody.get('client_id')!r} azp={ibody.get('azp')!r}")
    check("introspect_iss_public", ibody.get("iss") == issuer)
    status, body = inside("POST", f"{token_url()}/introspect", {
        "token": access, "client_id": "workspace-backup"})
    record("introspect_by_public_client", status, body)
    check("public_client_cannot_introspect", status in (400, 401, 403)
          or body.get("active") is not True, f"status={status} body={body}")
    status, body = inside("POST", f"{token_url()}/introspect", {"token": access},
                          basic="dtaas-workspace:wrong")
    check("introspect_wrong_secret_refused", status in (400, 401, 403),
          f"status={status}")
    status, body = introspect("not-a-token")
    record("introspect_invalid", status, body)
    check("introspect_invalid_inactive", body == {"active": False}, f"{status} {body}")

    # --- Login client with PKCE and nonce (LR-2) ------------------------
    lverifier, lchallenge = pkce_pair()
    nonce = secrets.token_urlsafe(12)
    lauth = user1.authorize({"client_id": "dtaas-workspace",
                             "redirect_uri": LOGIN_REDIRECT, "response_type": "code",
                             "scope": "openid profile", "state": "x",
                             "nonce": nonce, "code_challenge": lchallenge,
                             "code_challenge_method": "S256"})
    note("login_client_consent", str(lauth["consent"]))
    status, lbody = inside("POST", token_url(), {
        "grant_type": "authorization_code",
        "code": query(lauth["location"]).get("code", ""),
        "redirect_uri": LOGIN_REDIRECT, "code_verifier": lverifier},
        basic=f"dtaas-workspace:{STATE['login_secret']}")
    check("login_redeem_with_pkce_and_secret", status == 200 and "id_token" in lbody,
          f"status={status}")
    if status == 200:
        idt = claims(lbody["id_token"])
        check("login_id_token_nonce", idt.get("nonce") == nonce)
        check("login_id_token_iss_public", idt.get("iss") == issuer)
        status, ibody = introspect(lbody["access_token"])
        record("introspect_login_token", status, ibody)
        note("introspect_login_token", f"client_id={ibody.get('client_id')} "
             f"username={ibody.get('username')}")

    # --- Revocation and disabling ---------------------------------------
    _, fresh = connect(user1)
    status, body = inside("POST", f"{INTERNAL}/realms/dtaas/{OIDC}/revoke", {
        "token": fresh["refresh_token"], "client_id": "workspace-backup",
        "token_type_hint": "refresh_token"})
    record("backup_revoke", status, body)
    check("public_revoke_200", status == 200, f"status={status} {body}")
    check("revoked_refresh_refused", refresh(fresh["refresh_token"])[0] == 400)
    status, ibody = introspect(fresh["access_token"])
    note("access_after_revoke_introspect", f"active={ibody.get('active')}")

    uid = STATE["users"]["dtaas/user1"]
    _, live = connect(user1)
    admin("PUT", f"/realms/dtaas/users/{uid}", json={"enabled": False})
    status, body = refresh(live["refresh_token"])
    record("backup_refresh_disabled_user", status, body)
    check("disabled_user_refresh_refused", status == 400, f"{status} {body}")
    status, ibody = introspect(live["access_token"])
    check("disabled_user_introspect_inactive", ibody.get("active") is False,
          f"active={ibody.get('active')}")
    admin("PUT", f"/realms/dtaas/users/{uid}", json={"enabled": True})
    note("refresh_after_reenable", f"status={refresh(live['refresh_token'])[0]}")

    _, live = connect(user1)
    reply = admin("DELETE", f"/realms/dtaas/users/{uid}/consents/workspace-backup")
    note("admin_revoke_consent", f"status={reply.status_code}")
    status, body = refresh(live["refresh_token"])
    check("admin_revoke_offline_refresh_refused", status == 400, f"{status} {body}")

    # The designed order: DTaaS login first, then Connect with Keycloak.
    user2 = BrowserUser(browser, "user2")
    lverifier, lchallenge = pkce_pair()
    lauth = user2.authorize({"client_id": "dtaas-workspace",
                             "redirect_uri": LOGIN_REDIRECT, "response_type": "code",
                             "scope": "openid profile", "state": "x",
                             "nonce": secrets.token_urlsafe(8),
                             "code_challenge": lchallenge,
                             "code_challenge_method": "S256"})
    _, login2 = inside("POST", token_url(), {
        "grant_type": "authorization_code",
        "code": query(lauth["location"]).get("code", ""),
        "redirect_uri": LOGIN_REDIRECT, "code_verifier": lverifier},
        basic=f"dtaas-workspace:{STATE['login_secret']}")
    auth2, u2 = connect(user2, shot="consent-after-dtaas-login")
    check("connect_after_dtaas_login_no_password", not auth2["login"])
    check("connect_after_dtaas_login_asks_consent", auth2["consent"])
    check("other_user_token_names_user2",
          claims(u2["access_token"]).get("preferred_username") == "user2")
    check("dtaas_session_survives_connect",
          introspect(login2["access_token"])[1].get("active") is True)
    status, _ = inside("POST", token_url(), {
        "grant_type": "refresh_token", "refresh_token": login2["refresh_token"]},
        basic=f"dtaas-workspace:{STATE['login_secret']}")
    check("dtaas_login_refreshes_after_connect", status == 200, f"status={status}")

    # --- Realm offline limits -------------------------------------------
    realm = admin("GET", "/realms/dtaas").json()
    check("realm_offline_idle_30_days", realm["offlineSessionIdleTimeout"] == 30 * 86400)
    check("realm_offline_max_180_days", realm["offlineSessionMaxLifespanEnabled"]
          and realm["offlineSessionMaxLifespan"] == 180 * 86400)

    # Enforcement, in realm `short`: idle 60 s, max 90 s.
    short_max = BrowserUser(browser, "user1", realm="short")
    _, kept = connect(short_max)
    short_idle = BrowserUser(browser, "user2", realm="short")
    _, idle = connect(short_idle)
    note("short_refresh_expires_in", str(kept.get("refresh_expires_in")))
    started, token_kept, outcome = time.time(), kept["refresh_token"], []
    while time.time() - started < 200:
        time.sleep(20)
        status, body = refresh(token_kept, realm="short")
        outcome.append((int(time.time() - started), status))
        if status != 200:
            break
        token_kept = body["refresh_token"]
    note("short_max_refreshes", str(outcome))
    check("offline_max_enforced_while_refreshing",
          outcome[-1][1] == 400 and 90 <= outcome[-1][0] <= 130, str(outcome[-1]))
    while time.time() - started < 200:
        time.sleep(10)
    status, body = refresh(idle["refresh_token"], realm="short")
    note("short_idle_after_200s", f"status={status} {body}")
    check("offline_idle_enforced", status == 400,
          f"after {int(time.time() - started)} s unused")

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    if failed:
        print("failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
