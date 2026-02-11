"""
Unit tests for the admin service.

Tests the /services endpoint and service discovery functionality.
"""

import os
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin.main import app, load_services, SERVICES_TEMPLATE_PATH


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_main_user(monkeypatch):
    """Set up mock MAIN_USER environment variable."""
    monkeypatch.setenv('MAIN_USER', 'testuser')


def test_root_endpoint(client):
    """Test the root endpoint returns service information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Workspace Admin Service"
    assert "endpoints" in data
    assert "/services" in data["endpoints"]


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_services_endpoint(client, mock_main_user):
    """Test the /services endpoint returns service list."""
    response = client.get("/services")
    assert response.status_code == 200
    
    services = response.json()
    
    # Check that we have the expected services
    assert "desktop" in services
    assert "vscode" in services
    assert "notebook" in services
    assert "lab" in services
    
    # Check desktop service structure
    desktop = services["desktop"]
    assert "name" in desktop
    assert "description" in desktop
    assert "endpoint" in desktop
    assert desktop["name"] == "Desktop"
    
    # Check that MAIN_USER is substituted correctly
    assert "testuser" in desktop["endpoint"]
    assert "{MAIN_USER}" not in desktop["endpoint"]


def test_services_endpoint_default_user(client, monkeypatch):
    """Test /services endpoint with default MAIN_USER."""
    # Remove MAIN_USER from environment
    monkeypatch.delenv('MAIN_USER', raising=False)
    
    response = client.get("/services")
    assert response.status_code == 200
    
    services = response.json()
    desktop = services["desktop"]
    
    # Should use default 'dtaas-user'
    assert "dtaas-user" in desktop["endpoint"]


def test_load_services_substitutes_main_user(mock_main_user):
    """Test that load_services correctly substitutes MAIN_USER."""
    services = load_services()
    
    # Check that {MAIN_USER} is replaced with 'testuser'
    desktop_endpoint = services["desktop"]["endpoint"]
    assert "testuser" in desktop_endpoint
    assert "{MAIN_USER}" not in desktop_endpoint


def test_load_services_preserves_structure():
    """Test that load_services preserves the service structure."""
    services = load_services()
    
    # Check all required services exist
    required_services = ["desktop", "vscode", "notebook", "lab"]
    for service_id in required_services:
        assert service_id in services
        assert "name" in services[service_id]
        assert "description" in services[service_id]
        assert "endpoint" in services[service_id]


def test_services_template_file_exists():
    """Test that the services template file exists."""
    assert SERVICES_TEMPLATE_PATH.exists()
    assert SERVICES_TEMPLATE_PATH.is_file()


def test_services_template_valid_json():
    """Test that the services template is valid JSON."""
    with open(SERVICES_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        services = json.load(f)
    
    # Should not raise an exception
    assert isinstance(services, dict)
    assert len(services) > 0
