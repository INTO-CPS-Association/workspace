"""Git backup support for workspace-admin."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import tomllib
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class RepoConfig:
    """Git backup repository configuration."""

    name: str
    repo_url: str
    branch: str
    username: str
    token: str
    git_dir: Path
    work_tree: Path

    @property
    def authenticated_url(self) -> str:
        """Return URL with HTTP basic credentials, if configured."""
        if not self.username or not self.token:
            return self.repo_url
        if self.repo_url.startswith("https://"):
            return self.repo_url.replace(
                "https://",
                f"https://{self.username}:{self.token}@",
                1,
            )
        return self.repo_url

    @property
    def sanitized_url(self) -> str:
        """Return a sanitized URL for logs."""
        split_url = urlsplit(self.repo_url)
        if "@" not in split_url.netloc:
            return self.repo_url
        return urlunsplit(
            (
                split_url.scheme,
                f"***@{split_url.netloc.split('@', maxsplit=1)[1]}",
                split_url.path,
                split_url.query,
                split_url.fragment,
            ),
        )


def _run_git_command(repo: RepoConfig, args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo.work_tree), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def load_git_backup_config(config_path: Path) -> List[RepoConfig]:
    """Parse git backup configuration file."""
    with open(config_path, "rb") as config_file:
        config = tomllib.load(config_file)

    workspace_dir = Path(config["WORKSPACE_DIR"])
    app_dir = Path(config["WORKSPACE_APP_DIR"])
    if not app_dir.is_absolute():
        app_dir = Path(config["HOME_DIR"]) / app_dir

    repos = []
    assets = config.get("assets", {})
    for name in ("private", "common"):
        if name not in assets:
            continue
        asset_config = assets[name]
        repos.append(
            RepoConfig(
                name=name,
                repo_url=asset_config["GIT_REPO_URL"],
                branch=asset_config.get("GIT_REPO_BRANCH", "main"),
                username=asset_config.get("GIT_REPO_USERNAME", ""),
                token=asset_config.get("GIT_REPO_TOKEN", ""),
                git_dir=workspace_dir / asset_config["GIT_DIR"],
                work_tree=app_dir / asset_config["GIT_WORK_TREE"],
            ),
        )
    return repos


def _configure_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("workspace-admin.git-backup")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )
    logger.addHandler(file_handler)
    return logger


class GitBackupManager:
    """Manages repository initialization and periodic synchronization."""

    def __init__(self, repos: List[RepoConfig], logger: logging.Logger):
        self.repos = repos
        self.logger = logger

    def initialize(self) -> None:
        """Initialize repositories and workspace links."""
        for repo in self.repos:
            try:
                self._initialize_repo(repo)
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                self.logger.error(
                    "Failed to initialize %s repository: %s",
                    repo.name,
                    error,
                )

    def sync_once(self) -> None:
        """Run a single pull/commit/push sync cycle for all repositories."""
        for repo in self.repos:
            try:
                self._sync_repo(repo)
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                self.logger.error("Failed to sync %s repository: %s", repo.name, error)

    def _initialize_repo(self, repo: RepoConfig) -> None:
        repo.git_dir.parent.mkdir(parents=True, exist_ok=True)
        repo.work_tree.parent.mkdir(parents=True, exist_ok=True)

        if not (repo.work_tree / ".git").exists():
            clone_command = [
                "git",
                "clone",
                "--branch",
                repo.branch,
                repo.authenticated_url,
                str(repo.work_tree),
            ]
            subprocess.run(clone_command, check=True, capture_output=True, text=True)
            self.logger.info("Cloned %s repository from %s", repo.name, repo.sanitized_url)

        _run_git_command(repo, ["config", "pull.rebase", "false"])
        _run_git_command(repo, ["config", "user.name", "workspace-admin"])
        _run_git_command(repo, ["config", "user.email", "workspace-admin@localhost"])

        if repo.authenticated_url != repo.repo_url:
            _run_git_command(repo, ["remote", "set-url", "origin", repo.authenticated_url])

        if repo.git_dir.exists() and not repo.git_dir.is_symlink():
            raise ValueError(
                "Cannot create configured GIT_DIR link for repository "
                f"'{repo.name}'. Remove the existing path or configure "
                "a different GIT_DIR location.",
            )

        if not repo.git_dir.exists():
            repo.git_dir.symlink_to(repo.work_tree, target_is_directory=True)

    def _sync_repo(self, repo: RepoConfig) -> None:
        _run_git_command(repo, ["fetch", "origin", repo.branch])
        _run_git_command(repo, ["pull", "--no-rebase", "-X", "ours", "origin", repo.branch])
        self.logger.info(
            "Pulled %s with merge strategy '-X ours' (local changes preferred on conflicts)",
            repo.name,
        )
        _run_git_command(repo, ["add", "-A"])

        status = _run_git_command(repo, ["status", "--porcelain"]).stdout.strip()
        if status:
            commit_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _run_git_command(repo, ["commit", "-m", f"workspace backup {commit_timestamp}"])
            _run_git_command(repo, ["push", "origin", repo.branch])
            self.logger.info("Committed and pushed changes for %s", repo.name)


def start_git_backup(
    config_path: Path,
    interval_seconds: int,
    stop_event: threading.Event,
) -> None:
    """Start background git backup worker if config exists."""
    if not config_path.exists():
        return

    app_dir = config_path.parent
    logger = _configure_logger(app_dir / "logs" / "workspace-admin.log")
    repos = load_git_backup_config(config_path)
    manager = GitBackupManager(repos, logger)
    manager.initialize()

    def backup_loop() -> None:
        while not stop_event.wait(interval_seconds):
            manager.sync_once()

    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
