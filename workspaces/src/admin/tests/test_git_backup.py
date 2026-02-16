"""Tests for git backup support."""

import logging
from types import SimpleNamespace
from pathlib import Path

from admin.git_backup import GitBackupManager, load_git_backup_config


def test_load_git_backup_config(tmp_path):
    """Git backup config parser returns private/common repository settings."""
    config_file = tmp_path / "config.env"
    config_file.write_text(
        """
HOME_DIR = "/home/user"
WORKSPACE_DIR = "/workspace"
WORKSPACE_APP_DIR = ".workspace"

[assets.private]
GIT_REPO_URL = "https://example.com/private.git"
GIT_REPO_BRANCH = "main"
GIT_REPO_USERNAME = "user"
GIT_REPO_TOKEN = "token"
GIT_DIR = "private"
GIT_WORK_TREE = "assets/private"

[assets.common]
GIT_REPO_URL = "https://example.com/common.git"
GIT_REPO_BRANCH = "main"
GIT_REPO_USERNAME = "user"
GIT_REPO_TOKEN = "token"
GIT_DIR = "common"
GIT_WORK_TREE = "assets/common"
""".strip(),
        encoding="utf-8",
    )
    repos = load_git_backup_config(config_file)
    assert len(repos) == 2
    assert repos[0].git_dir == Path("/workspace/private")
    assert repos[0].work_tree == Path("/home/user/.workspace/assets/private")


def test_initialize_creates_workspace_symlink(tmp_path, monkeypatch):
    """Repository initialization creates workspace symlink to work tree."""
    workspace_dir = tmp_path / "workspace"
    app_dir = tmp_path / "app"
    config_file = tmp_path / "config.env"
    config_file.write_text(
        f"""
HOME_DIR = "/home/user"
WORKSPACE_DIR = "{workspace_dir}"
WORKSPACE_APP_DIR = "{app_dir}"

[assets.private]
GIT_REPO_URL = "https://example.com/private.git"
GIT_REPO_BRANCH = "main"
GIT_REPO_USERNAME = "user"
GIT_REPO_TOKEN = "token"
GIT_DIR = "private"
GIT_WORK_TREE = "assets/private"
""".strip(),
        encoding="utf-8",
    )
    repos = load_git_backup_config(config_file)

    def fake_run(command, check, capture_output, text):  # pylint: disable=unused-argument
        """Simulate git clone and no-op for other git commands."""
        if command[0:2] == ["git", "clone"]:
            work_tree = Path(command[-1])
            work_tree.mkdir(parents=True, exist_ok=True)
            (work_tree / ".git").mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("admin.git_backup.subprocess.run", fake_run)
    manager = GitBackupManager(repos, logging.getLogger("test-git-backup"))
    manager.initialize()

    assert repos[0].git_dir.is_symlink()
    assert repos[0].git_dir.resolve() == repos[0].work_tree
