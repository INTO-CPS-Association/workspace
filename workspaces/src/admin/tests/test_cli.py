"""CLI tests for admin.main."""

import json

import pytest

from admin.main import cli


def test_cli_list_services(monkeypatch, capsys):
    """CLI can print services and exit."""
    monkeypatch.setattr("sys.argv", ["workspace-admin", "--list-services"])
    with pytest.raises(SystemExit) as exc_info:
        cli()
    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert "desktop" in output


def test_cli_version(monkeypatch):
    """CLI version flag exits successfully."""
    monkeypatch.setattr("sys.argv", ["workspace-admin", "--version"])
    with pytest.raises(SystemExit) as exc_info:
        cli()
    assert exc_info.value.code == 0
