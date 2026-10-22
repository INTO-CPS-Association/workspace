"""Spike S3: answers Oathkeeper as login-relay would, and logs what it gets.

/token/introspect answers the LOGIN_RELAY.md contract for token "good"
and {"active": false} otherwise; /authz/workspace/<user> logs the
remote_json payload; /calls returns the counts and the last payload.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

ANSWER = {"active": True, "username": "user1", "sub": "42",
          "client_id": "dtaas-login-uid", "scope": "openid",
          "exp": 4102444800, "token_type": "Bearer",
          "ext": {"groups": ["dtaas"]}}
STATE = {"introspect": 0, "authz": 0, "payload": None}


class Handler(BaseHTTPRequestHandler):
    """Fake login-relay."""

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # pylint: disable=invalid-name
        """Introspection and authorization."""
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        if self.path == "/token/introspect":
            STATE["introspect"] += 1
            token = parse_qs(raw).get("token", [""])[0]
            self._send(200, ANSWER if token == "good" else {"active": False})
        elif self.path.startswith("/authz/workspace/"):
            STATE["authz"] += 1
            STATE["payload"] = json.loads(raw)
            self._send(200, {})
        else:
            self._send(404, {})

    def do_GET(self):  # pylint: disable=invalid-name
        """Counters for the probe."""
        self._send(200, STATE if self.path == "/calls" else {})


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
