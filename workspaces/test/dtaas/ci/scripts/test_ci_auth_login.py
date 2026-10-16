"""
Tests for ci_auth_login.py, the headless Dex login used by the CI
composition tests.
"""

import http.server
import importlib.util
import threading
from pathlib import Path

import pytest
import requests
from requests.cookies import RequestsCookieJar, create_cookie, get_cookie_header

SCRIPT = Path(__file__).with_name("ci_auth_login.py")


def _load_module():
    """Load ci_auth_login.py by path, since scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("ci_auth_login", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci_auth_login = _load_module()


def test_secure_cookie_is_not_sent_to_other_http_hosts():
    """Away from localhost, Secure cookies still need https."""
    jar = RequestsCookieJar()
    jar.set_policy(ci_auth_login.BrowserLikeCookiePolicy())
    jar.set_cookie(create_cookie("oauth_state", "abc", domain="example.com", secure=True))

    def header(url):
        return get_cookie_header(jar, requests.Request("GET", url).prepare())

    assert header("http://example.com/") is None
    assert header("https://example.com/") == "oauth_state=abc"


class _Handler(http.server.BaseHTTPRequestHandler):
    """A tiny site:

    - /protected redirects to /ok, like a login wall.
    - /set sets a Secure cookie and redirects to /echo, like login-relay
      setting oauth_state before sending the browser to Dex and back.
    - /echo answers with the Cookie header it received.
    - anything else answers 200 with an empty body.
    """

    def do_GET(self):  # pylint: disable=invalid-name
        """Answer the test paths."""
        body = b""
        if self.path == "/protected":
            self.send_response(302)
            self.send_header("Location", "/ok")
        elif self.path == "/set":
            self.send_response(302)
            self.send_header("Set-Cookie", "oauth_state=abc; Secure; HttpOnly; Path=/")
            self.send_header("Location", "/echo")
        else:
            self.send_response(200)
            if self.path == "/echo":
                body = self.headers.get("Cookie", "").encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        """Keep test output quiet."""


@pytest.fixture(name="server_url")
def fixture_server_url():
    """Run _Handler on a free local port for the duration of a test."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_secure_cookie_is_sent_to_http_localhost(server_url):
    """Like a browser, the session sends Secure cookies to plain-HTTP
    localhost, on redirects and on later requests alike."""
    session = ci_auth_login.new_session(verify=True)

    after_redirect = session.get(f"{server_url}/set", timeout=10)
    later = session.get(f"{server_url}/echo", timeout=10)

    assert after_redirect.text == "oauth_state=abc"
    assert later.text == "oauth_state=abc"


def test_redirect_is_not_authenticated_access(server_url):
    """A 200 reached only by following a redirect (e.g. to a login page)
    must not count as authenticated access."""
    session = ci_auth_login.new_session(verify=True)

    assert ci_auth_login.verify_authenticated_access(session, f"{server_url}/protected") is False


def test_direct_200_is_authenticated_access(server_url):
    """The protected URL answering 200 itself is authenticated access."""
    session = ci_auth_login.new_session(verify=True)

    assert ci_auth_login.verify_authenticated_access(session, f"{server_url}/ok") is True
