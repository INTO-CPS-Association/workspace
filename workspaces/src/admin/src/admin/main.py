"""CLI entrypoint for workspace admin service."""

import argparse
import json
import os
import sys
import threading
from pathlib import Path

import uvicorn

from admin.api import create_app
from admin.git_backup import start_git_backup
from admin.services import load_services


def _default_config_path() -> Path:
    return Path(os.getenv("HOME", "/home/dtaas-user")) / ".workspace" / "config.env"


def cli() -> None:
    """Command-line interface for the workspace admin service."""
    parser = argparse.ArgumentParser(
        description=(
            "Workspace Admin Service - "
            "Service discovery and git backup for DTaaS workspaces"
        ),
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the service to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ADMIN_SERVER_PORT", "8091")),
        help="Port to bind the service to (default: $ADMIN_SERVER_PORT or 8091)",
    )
    parser.add_argument(
        "--path-prefix",
        default=os.getenv("PATH_PREFIX", "dtaas-user"),
        help="Path prefix for API routes (e.g., 'dtaas-user' for routes at /dtaas-user/services)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="List available services and exit",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to git backup config file (default: $HOME/.workspace/config.env)",
    )
    parser.add_argument(
        "--git-sync-interval",
        type=int,
        default=300,
        help="Git backup interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--disable-git-backup",
        action="store_true",
        help="Disable git backup worker",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    args = parser.parse_args()

    path_prefix = args.path_prefix.strip("/")
    if path_prefix:
        os.environ["PATH_PREFIX"] = path_prefix
        prefix_display = f"/{path_prefix}"
    else:
        prefix_display = ""

    if args.list_services:
        services = load_services(path_prefix)
        print(json.dumps(services, indent=2))
        sys.exit(0)

    print(f"Starting Workspace Admin Service on {args.host}:{args.port}")
    print("Service endpoints:")
    print(f"  - http://{args.host}:{args.port}{prefix_display}/services")
    print(f"  - http://{args.host}:{args.port}{prefix_display}/health")
    print(f"  - http://{args.host}:{args.port}{prefix_display}/")

    app = create_app(path_prefix)

    if not args.disable_git_backup:
        stop_event = threading.Event()
        start_git_backup(args.config, args.git_sync_interval, stop_event)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    cli()
