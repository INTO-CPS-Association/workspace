"""
Unit tests for the admin service.

Tests the /services endpoint and service discovery functionality.
"""

import json

import pytest
from fastapi.testclient import TestClient

from admin.main import app, load_services, SERVICES_TEMPLATE_PATH


@pytest.fixture(name='test_client')
def fixture_test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(name='setup_mock_main_user')
def fixture_mock_main_user(monkeypatch):
    """Set up mock MAIN_USER environment variable."""
    monkeypatch.setenv('MAIN_USER', 'testuser')


def test_root_endpoint(test_client):
    """Test the root endpoint returns service information."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Workspace Admin Service"
    assert "endpoints" in data
    assert "/services" in data["endpoints"]


def test_health_check(test_client):
    """Test the health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_services_endpoint(test_client, setup_mock_main_user):
    """Test the /services endpoint returns service list."""
    # setup_mock_main_user fixture sets MAIN_USER='testuser'
    _ = setup_mock_main_user  # Mark as intentionally used
    response = test_client.get("/services")
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


def test_services_endpoint_default_user(test_client, monkeypatch):
    """Test /services endpoint with default MAIN_USER."""
    # Remove MAIN_USER from environment
    monkeypatch.delenv('MAIN_USER', raising=False)

    response = test_client.get("/services")
    assert response.status_code == 200

    services = response.json()
    desktop = services["desktop"]

    # Should use default 'dtaas-user'
    assert "dtaas-user" in desktop["endpoint"]


def test_load_services_substitutes_main_user(setup_mock_main_user):
    """Test that load_services correctly substitutes MAIN_USER."""
    # setup_mock_main_user fixture sets MAIN_USER='testuser'
    _ = setup_mock_main_user  # Mark as intentionally used
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


def test_cli_list_services(monkeypatch, capsys):
    """Test CLI --list-services flag."""
    import sys
    monkeypatch.setenv('MAIN_USER', 'clitest')
    monkeypatch.setattr(sys, 'argv', ['workspace-admin', '--list-services'])

    from admin.main import cli

    with pytest.raises(SystemExit) as exc_info:
        cli()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert "desktop" in output
    assert "clitest" in output["desktop"]["endpoint"]


def test_cli_version(monkeypatch):
    """Test CLI --version flag."""
    import sys
    monkeypatch.setattr(sys, 'argv', ['workspace-admin', '--version'])

    from admin.main import cli

    with pytest.raises(SystemExit) as exc_info:
        cli()

    # argparse exits with 0 for --version
    assert exc_info.value.code == 0


def test_load_services_with_missing_endpoint():
    """Test load_services handles services without endpoint field."""
    services = load_services()
    # All services should have endpoint field, even if empty
    for service_info in services.values():
        assert 'endpoint' in service_info


def test_services_endpoint_json_structure(test_client):
    """Test that services endpoint returns proper JSON structure."""
    response = test_client.get("/services")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    services = response.json()
    # Verify it's a dictionary with string keys
    assert isinstance(services, dict)
    for key, value in services.items():
        assert isinstance(key, str)
        assert isinstance(value, dict)
        assert "name" in value
        assert "description" in value
        assert "endpoint" in value


def test_root_endpoint_version(test_client):
    """Test that root endpoint includes version."""
    response = test_client.get("/")
    data = response.json()
    assert "version" in data
    assert data["version"] == "0.1.0"


def test_health_endpoint_returns_json(test_client):
    """Test that health endpoint returns JSON."""
    response = test_client.get("/health")
    assert response.headers["content-type"] == "application/json"
