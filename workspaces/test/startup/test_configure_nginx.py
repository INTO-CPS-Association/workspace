"""
Tests for startup/configure_nginx.py, which fills the nginx template from the
environment when the container starts.
"""

import importlib.util
import re
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src" / "startup"
TEMPLATE = SRC_DIR / "nginx.conf"
PLACEHOLDER = re.compile(r"\{[A-Z_]+\}")

VALID_ENV = {
    "MAIN_USER": "user1",
    "JUPYTER_SERVER_PORT": "8090",
    "CODE_SERVER_PORT": "8054",
    "NO_VNC_PORT": "6901",
    "ADMIN_SERVER_PORT": "8091",
}


def _load_module():
    """Load configure_nginx.py by path, since startup/ is not a package."""
    spec = importlib.util.spec_from_file_location(
        "configure_nginx", SRC_DIR / "configure_nginx.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


configure_nginx = _load_module()


def test_render_fills_the_real_template():
    """Every placeholder in the shipped template gets a value."""
    rendered = configure_nginx.render(TEMPLATE.read_text(), VALID_ENV)

    assert "/user1/services" in rendered
    assert "127.0.0.1:6901" in rendered
    assert not PLACEHOLDER.search(rendered)


@pytest.mark.parametrize("name", sorted(VALID_ENV))
def test_missing_variable_is_named(name):
    """A missing variable is reported by name, not as a KeyError."""
    env = dict(VALID_ENV)
    del env[name]

    with pytest.raises(configure_nginx.ConfigError, match=name):
        configure_nginx.render(TEMPLATE.read_text(), env)


@pytest.mark.parametrize(
    "main_user",
    ["a@b", "a'b", "a;rm -rf /", "a b", "a/b", "-a", "ü", "a" * 33],
)
def test_unsafe_main_user_rejected(main_user):
    """Names that could break out of the nginx config are refused."""
    env = {**VALID_ENV, "MAIN_USER": main_user}

    with pytest.raises(configure_nginx.ConfigError, match="MAIN_USER"):
        configure_nginx.render(TEMPLATE.read_text(), env)


@pytest.mark.parametrize("main_user", ["User.1", "a-b_c"])
def test_valid_main_user_accepted(main_user):
    """Names that usermod accepts today keep working."""
    env = {**VALID_ENV, "MAIN_USER": main_user}

    rendered = configure_nginx.render(TEMPLATE.read_text(), env)

    assert f"/{main_user}/services" in rendered


@pytest.mark.parametrize("port", ["80a", "0", "65536", ""])
def test_bad_port_rejected(port):
    """Ports must be numbers in the TCP range."""
    env = {**VALID_ENV, "ADMIN_SERVER_PORT": port}

    with pytest.raises(configure_nginx.ConfigError, match="ADMIN_SERVER_PORT"):
        configure_nginx.render(TEMPLATE.read_text(), env)


def test_main_rewrites_file(tmp_path):
    """main() fills the config file in place."""
    config = tmp_path / "nginx.conf"
    config.write_text(TEMPLATE.read_text())

    assert configure_nginx.main(str(config), VALID_ENV) == 0
    assert not PLACEHOLDER.search(config.read_text())


def test_main_refuses_without_writing(tmp_path, capsys):
    """On a bad value main() reports it and leaves the file alone."""
    config = tmp_path / "nginx.conf"
    config.write_text(TEMPLATE.read_text())
    before = config.read_bytes()

    result = configure_nginx.main(str(config), {**VALID_ENV, "MAIN_USER": "a;b"})

    assert result == 1
    assert config.read_bytes() == before
    assert "MAIN_USER" in capsys.readouterr().err
