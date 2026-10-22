"""Spike S4: seeds the spike Keycloak through the admin REST API.

Creates realm `dtaas` with the offline-session settings of
STORAGE_KEYCLOAK.md, realm `short` with the same clients but offline
limits of seconds (to watch them enforced), users user1 and user2, the
confidential login-relay client `dtaas-workspace` and the public
`workspace-backup` client. Writes secrets to state.json (not committed).
AUDIENCE_MAPPER=0 leaves the mapper off `workspace-backup`, to show
introspection refusing its tokens. Run with: python3 -I setup.py
"""

# The spike's dependencies are not in the CI lint environment.
# pylint: disable=import-error

import json
import os
import time
from pathlib import Path

import requests

BASE = "http://localhost:8180/auth"
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("STATE", HERE / "state.json"))
PASSWORD = "Spike-user-pw-2026!"
LOGIN_SECRET = "spike-dtaas-workspace-secret"
DAY = 86400
# Keycloak introspection answers active only to a client in the token's
# aud, so both clients put login-relay's client there.
AUDIENCE = [{"name": "dtaas-workspace-audience", "protocol": "openid-connect",
             "protocolMapper": "oidc-audience-mapper",
             "config": {"included.client.audience": "dtaas-workspace",
                        "access.token.claim": "true",
                        "introspection.token.claim": "true"}}]
AUDIENCE_ON = os.environ.get("AUDIENCE_MAPPER", "1") == "1"

REALMS = {
    "dtaas": {"offlineSessionIdleTimeout": 30 * DAY,
              "offlineSessionMaxLifespanEnabled": True,
              "offlineSessionMaxLifespan": 180 * DAY},
    "short": {"offlineSessionIdleTimeout": 60,
              "offlineSessionMaxLifespanEnabled": True,
              "offlineSessionMaxLifespan": 90},
}


def admin_token() -> str:
    """Password grant on master's admin-cli, after Keycloak is up."""
    for _ in range(60):
        try:
            reply = requests.post(
                f"{BASE}/realms/master/protocol/openid-connect/token", timeout=10,
                data={"grant_type": "password", "client_id": "admin-cli",
                      "username": "admin", "password": "Spike-admin-pw-2026!"})
            if reply.status_code == 200:
                return reply.json()["access_token"]
        except requests.ConnectionError:
            pass
        time.sleep(5)
    raise RuntimeError("Keycloak did not come up")


def main() -> None:
    """Creates both realms."""
    headers = {"Authorization": f"Bearer {admin_token()}"}

    def post(path: str, body: dict) -> None:
        reply = requests.post(f"{BASE}/admin{path}", json=body,
                              headers=headers, timeout=30)
        if reply.status_code not in (201, 204, 409):
            raise RuntimeError(f"{path}: {reply.status_code} {reply.text}")

    for realm, limits in REALMS.items():
        # Start from scratch so consent is asked again on every run.
        requests.delete(f"{BASE}/admin/realms/{realm}", headers=headers, timeout=30)
        post("/realms", {"realm": realm, "enabled": True,
                         "accessTokenLifespan": 300, **limits})
        for user in ("user1", "user2"):
            post(f"/realms/{realm}/users", {
                "username": user, "enabled": True, "email": f"{user}@example.org",
                "emailVerified": True, "firstName": user, "lastName": "Spike",
                "credentials": [{"type": "password", "value": PASSWORD,
                                 "temporary": False}]})
        post(f"/realms/{realm}/clients", {
            "clientId": "dtaas-workspace", "protocol": "openid-connect",
            "publicClient": False, "secret": LOGIN_SECRET,
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "redirectUris": ["https://dtaas.example.org/login-relay/callback"],
            "attributes": {"pkce.code.challenge.method": "S256"},
            "protocolMappers": AUDIENCE})
        post(f"/realms/{realm}/clients", {
            "clientId": "workspace-backup", "protocol": "openid-connect",
            "publicClient": True, "consentRequired": True,
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
            "redirectUris": [
                "https://dtaas.example.org/login-relay/oauth/keycloak/callback"],
            "webOrigins": [],
            "attributes": {"pkce.code.challenge.method": "S256"},
            "protocolMappers": AUDIENCE if AUDIENCE_ON else []})
    users = {}
    for realm in REALMS:
        for user in ("user1", "user2"):
            found = requests.get(f"{BASE}/admin/realms/{realm}/users",
                                 params={"username": user, "exact": "true"},
                                 headers=headers, timeout=30).json()
            users[f"{realm}/{user}"] = found[0]["id"]
    STATE.write_text(json.dumps({"password": PASSWORD,
                                 "login_secret": LOGIN_SECRET,
                                 "users": users}, indent=2), encoding="utf-8")
    STATE.chmod(0o600)
    print(f"seeded; state in {STATE}")


if __name__ == "__main__":
    main()
