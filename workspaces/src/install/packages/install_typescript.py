"""Installs Node.js and TypeScript toolchain."""
import subprocess

from installation_util import get_dependencies_for_package

get_dependencies_for_package("typescript").default_installation()

# Direct npm globals to /usr/local so binaries land in /usr/local/bin
# without extra symlinks — both at build time and for user installs at runtime.
subprocess.run(
    ["npm", "config", "set", "prefix", "/usr/local"],
    check=True
    )

subprocess.run(
    [
        "npm", "install", "-g",
        "--cache", "/tmp/npm-cache",
        "typescript", "tsx", "@types/node"
    ],
    check=True
    )
