"""Unit tests for admin API and service templates."""

import json

import pytest
from fastapi.testclient import TestClient

from admin.api import create_app
from admin.services import SERVICES_TEMPLATE_PATH, load_services


@pytest.fixture(name="test_client")
def fixture_test_client():
    """Create default app test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(name="test_client_with_prefix")
def fixture_test_client_with_prefix():
    """Create prefixed app test client."""
    app = create_app(path_prefix="user1")
    return TestClient(app)


def test_root_endpoint(test_client):
    """Root endpoint returns service metadata."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Workspace Admin Service"
    assert "endpoints" in data
    assert "/services" in data["endpoints"]


def test_health_check(test_client):
    """Health endpoint returns healthy status."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_services_endpoint(test_client):
    """Services endpoint returns known services."""
    response = test_client.get("/services")
    assert response.status_code == 200
    services = response.json()
    assert "desktop" in services
    assert "vscode" in services
    assert "notebook" in services
    assert "lab" in services


def test_load_services_preserves_structure():
    """Service template loader returns expected keys."""
    services = load_services()
    for service_id in ["desktop", "vscode", "notebook", "lab"]:
        assert service_id in services
        assert "name" in services[service_id]
        assert "description" in services[service_id]
        assert "endpoint" in services[service_id]


def test_services_template_file_exists():
    """Services template file is present."""
    assert SERVICES_TEMPLATE_PATH.exists()
    assert SERVICES_TEMPLATE_PATH.is_file()


def test_services_template_valid_json():
    """Services template file contains valid JSON."""
    with open(SERVICES_TEMPLATE_PATH, "r", encoding="utf-8") as service_file:
        services = json.load(service_file)
    assert isinstance(services, dict)
    assert len(services) > 0


def test_services_endpoint_json_structure(test_client):
    """Services endpoint returns JSON content type."""
    response = test_client.get("/services")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


def test_root_endpoint_with_prefix(test_client_with_prefix):
    """Root endpoint works when path prefix is configured."""
    response = test_client_with_prefix.get("/user1/")
    assert response.status_code == 200
    assert response.json()["service"] == "Workspace Admin Service"


def test_services_endpoint_with_prefix(test_client_with_prefix):
    """Services endpoint works when path prefix is configured."""
    response = test_client_with_prefix.get("/user1/services")
    assert response.status_code == 200
    assert "desktop" in response.json()


def test_health_endpoint_with_prefix(test_client_with_prefix):
    """Health endpoint works when path prefix is configured."""
    response = test_client_with_prefix.get("/user1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_path_prefix_not_accessible_without_prefix(test_client_with_prefix):
    """Root-level route is hidden when app uses path prefix."""
    response = test_client_with_prefix.get("/services")
    assert response.status_code == 404
