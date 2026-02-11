"""
FastAPI application for workspace service discovery.

This service provides a /services endpoint that returns a JSON object
containing information about all available services in the workspace.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Workspace Admin Service",
    description="Service discovery and management for DTaaS workspace",
    version="0.1.0"
)

# Path to services template
SERVICES_TEMPLATE_PATH = Path(__file__).parent / "services_template.json"


def load_services() -> Dict[str, Any]:
    """
    Load services from template and substitute environment variables.
    
    Returns:
        Dictionary containing service information with environment variables substituted.
    """
    # Read the services template
    with open(SERVICES_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        services = json.load(f)
    
    # Get MAIN_USER from environment, default to 'dtaas-user'
    main_user = os.getenv('MAIN_USER', 'dtaas-user')
    
    # Substitute {MAIN_USER} in endpoint values
    for service_id, service_info in services.items():
        if 'endpoint' in service_info:
            service_info['endpoint'] = service_info['endpoint'].replace(
                '{MAIN_USER}', main_user
            )
    
    return services


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint providing service information."""
    return {
        "service": "Workspace Admin Service",
        "version": "0.1.0",
        "endpoints": {
            "/services": "Get list of available workspace services",
            "/health": "Health check endpoint"
        }
    }


@app.get("/services")
async def get_services() -> JSONResponse:
    """
    Get list of available workspace services.
    
    Returns:
        JSONResponse containing service information.
    """
    services = load_services()
    return JSONResponse(content=services)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
