"""
Goes through the nginx config file and replaces all placeholders with values
from the environment.

The values are validated before anything is written: they end up inside nginx
paths, regexes and quoted strings, so a malformed one could change what the
config means instead of just failing.
"""

import os
import re
import sys
from collections.abc import Mapping

NGINX_FILE = "/etc/nginx/nginx.conf"

# shadow's own username charset (what usermod in dtaas_shim.sh accepts),
# minus the Samba "$" suffix. Nothing in it is special to nginx.
MAIN_USER_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,31}")

# Placeholder in the template -> environment variable holding the port.
# Confusingly, it is the env variable "NO_VNC_PORT" that defines the port that
# KASMvnc serves its VNC through. This is set by the underlying KASM base image.
PORT_PLACEHOLDERS = {
    "{JUPYTER_SERVER_PORT}": "JUPYTER_SERVER_PORT",
    "{CODE_SERVER_PORT}": "CODE_SERVER_PORT",
    "{VNC_PORT}": "NO_VNC_PORT",
    "{ADMIN_SERVER_PORT}": "ADMIN_SERVER_PORT",
}


class ConfigError(ValueError):
    """An environment variable is missing or unusable; the message names it."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None:
        raise ConfigError(f"environment variable {name} is not set")
    return value


def _main_user(env: Mapping[str, str]) -> str:
    value = _required(env, "MAIN_USER")
    if not MAIN_USER_PATTERN.fullmatch(value):
        raise ConfigError(
            f"MAIN_USER {value!r} is not a valid user name: use up to 32 "
            "letters, digits, '_', '.' or '-', not starting with '.' or '-'"
        )
    return value


def _port(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    if not (value.isascii() and value.isdigit() and 1 <= int(value) <= 65535):
        raise ConfigError(f"{name} {value!r} is not a port number (1-65535)")
    return value


def render(template: str, env: Mapping[str, str]) -> str:
    """
    Return the template with every placeholder replaced from ``env``.

    Raises:
        ConfigError: If a variable is missing or holds an unusable value.
    """
    main_user = _main_user(env)
    replacements = {
        "{MAIN_USER}": main_user,
        # The allowed charset needs no URL escaping, so both forms agree.
        "{WORKSPACE_BASE_URL_DECODED}": "/" + main_user,
        "{WORKSPACE_BASE_URL_ENCODED}": "/" + main_user,
    }
    for placeholder, name in PORT_PLACEHOLDERS.items():
        replacements[placeholder] = _port(env, name)

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def main(path: str = NGINX_FILE, env: Mapping[str, str] | None = None) -> int:
    """
    Fill the config file at ``path`` in place from ``env``.

    Returns:
        0 on success; 1 if a variable is unusable, in which case the file is
        left untouched and the reason is printed to stderr.
    """
    with open(path, "r", encoding="utf-8") as config_file:
        template = config_file.read()
    try:
        rendered = render(template, os.environ if env is None else env)
    except ConfigError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8") as config_file:
        config_file.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
