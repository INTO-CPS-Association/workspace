from installation_util import get_dependencies_for_package

get_dependencies_for_package(
    "uv",
    resulting_binaries=["uv", "uvx"]
    ).default_installation()
