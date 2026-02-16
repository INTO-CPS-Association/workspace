"""Service template loading utilities for workspace admin."""

import json
from pathlib import Path
from typing import Any, Dict

SERVICES_TEMPLATE_PATH = Path(__file__).parent / "services_template.json"


def load_services(path_prefix: str = "") -> Dict[str, Any]:
    """
    Load services from template and substitute environment variables.

    Returns:
        Dictionary containing service information with environment
        variables substituted.
    """
    with open(SERVICES_TEMPLATE_PATH, "r", encoding="utf-8") as service_file:
        services = json.load(service_file)

    for service_info in services.values():
        if "endpoint" in service_info:
            service_info["endpoint"] = service_info["endpoint"].replace(
                "{PATH_PREFIX}",
                path_prefix,
            )

    return services
