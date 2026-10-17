# Workspace storage backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Tasks are in [tasks](../tasks/102-s3-backup.md) and use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Back up workspace assets to git or S3, with Keycloak and
GitLab connections managed from a page, a CLI or `config.toml`.

**Architecture:** workspace-admin gains a backend-neutral scheduler
(`admin/backup`), an S3 backend that drives `rclone`, a login core
that owns connections, credentials and session checks, an asset
configuration package with a safe writer, a composition root that
builds backends, and two clients (a static page behind nginx and a CLI
on a Unix socket). Groups G0 to G8 of the
[roadmap](../FEATURE_ROADMAP.md) are built in dependency order; each
lands as its own pull requests.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, standard-library
`urllib`/`xml.etree`/`fcntl`/`hmac`, `rclone`, SeaweedFS 4.40+,
Keycloak, GitLab, nginx, Docker Compose.

**Spec:** [specs/102-s3-backup.md](../specs/102-s3-backup.md), with
the design in [design/storage](../design/storage/README.md).

## Global Constraints

- Python `^3.12`; no new runtime dependency in `pyproject.toml`.
- `rclone` pinned by version and SHA-256 in the Dockerfile.
- SeaweedFS image `>= 4.40`.
- Asset names `^[a-z0-9]{1,63}$`, defined once in `admin/assets`.
- Files holding secrets or config: mode `0600`, written by temp file,
  `fsync`, rename.
- Admin TCP listener `127.0.0.1:${ADMIN_SERVER_PORT}`; control socket
  in `/tmp/workspace-admin-<uid>/` with mode `0700`.
- OAuth: PKCE S256 only; `state` single use, 10 minutes.
- STS session `S3_SESSION_SECONDS`, default `3600`; `S3_MAX_DELETE`
  default `1000`; noncurrent versions expire after `30` days.
- Shutdown within `8` seconds.
- New files under 250 lines; functions under 25 lines; files already
  over 250 lines (`git/sync.py`, `git/config.py`, `git/bootstrap.py`)
  do not grow; pylint `--fail-under=9.0`; coverage not below the G1
  baseline.
- Every pull request updates the docs it makes stale:
  `workspaces/src/admin/README.md`, `DOCUMENTATION.md`, the repository
  `CLAUDE.md` layout section, and `docs/CHANGELOG.md`.
- Test command, from `workspaces/src/admin`:

  ```bash
  poetry run pylint src/admin tests --rcfile=../../../.pylintrc --fail-under=9.0
  poetry run pytest --cov=admin
  ```

## Review Focus

1. **Hand edit during a page save.** Expect `config_changed` and no
   write. Test: `test_writer_refuses_changed_file` (G1).
2. **Crash between receiving and saving a rotated refresh token.**
   Expect the old file intact and `login_expired` at worst, never a
   half-written file. Test: `test_store_save_is_atomic` (G2).
3. **Unmounted or emptied asset folder.** Expect no `rclone` call and
   `s3_empty_source`. Test: `test_sync_refuses_empty_tree` (G2).
4. **Keycloak or STS down while git assets exist.** Expect git assets
   to sync and S3 assets to report `s3_unreachable` or
   `login_unreachable`. Test: `test_round_isolates_connection_failure`
   (G3).
5. **STS session expiring during a long upload.** Expect
   `s3_auth_failed`, then a resumed upload next round. Test:
   `test_expired_session_is_retried_next_round` (G3).

## File structure

All paths below `workspaces/src/admin/src/admin/` unless noted.

| Group | Create | Modify |
| :--- | :--- | :--- |
| G1 | `backup/{__init__,base,errors,status,scheduler}.py`, `git/backend.py`, `assets/{__init__,model,loader,writer}.py`, `wiring.py` | `main.py`, `api.py`, `git/{config,status,scheduler,bootstrap,sync}.py` (imports move to `backup`), `workspaces/src/startup/custom_startup.sh`, `workspaces/test/dtaas/compose*.yml` (`cap_drop`) |
| G2 | `s3/{__init__,settings,runner,errors,backend}.py`, `login/{__init__,types,store}.py` | `wiring.py`, `workspaces/Dockerfile.ubuntu.noble.xfce`, `workspaces/test/dtaas/compose*.yml` |
| G3 | `login/{http,providers,pkce,pending,flow,owner,credentials,session,sts,errors}.py`, `web/{__init__,callbacks,auth,control}.py`, `server.py` | `main.py`, `backup/status.py`, `workspaces/src/startup/nginx.conf` |
| G4 | `cli/{__init__,client,commands}.py` | `main.py` |
| G5 | — | `login/providers.py`, `login/owner.py`, `git/{auth,backend}.py`, `assets/loader.py` |
| G6 | `web/{config_routes,csrf,headers}.py`, `web/static/{index.html,app.js}` | `server.py`, `workspaces/src/startup/nginx.conf` |
| G7 | DTaaS: `<target deployment>/storage/{provision.sh,s3.json.tmpl,iam.json.tmpl}` (target decided in T702) | DTaaS: the target deployment's `docker-compose.yml`, docs, `mkdocs.yml`, `mkdocs-github.yml` |

Tests mirror modules under `tests/unit/`; fakes go to
`tests/helpers/{fake_rclone,fake_idp,fake_sts}.py`; container tests to
`tests/integration/`.

## Interfaces between groups

```python
# backup/errors.py (G1). SyncErrorKind moves here and is renamed; no copy.
class BackupErrorKind(StrEnum): ...    # today's values + kinds of design 3
class BackupError(Exception):
    kind: BackupErrorKind
class BackupStopped(Exception): ...

# backup/base.py (G1)
BackendKind = Literal["git", "s3"]
class Backend(Protocol):
    name: str
    kind: BackendKind
    def prepare(self, stop_event: threading.Event) -> None: ...
    def sync(self, stop_event: threading.Event) -> None: ...   # raises BackupError

# backup/status.py (G1, G3)
class BackupStatus:
    def set_assets(self, kinds: dict[str, BackendKind]) -> None: ...
    def record_success(self, name: str) -> None: ...
    def record_failure(self, name: str, kind: BackupErrorKind) -> None: ...
    def set_connection(self, provider: ProviderName, state: ConnectionState) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...

# backup/scheduler.py (G1)
class Scheduler:
    def request_reload(self) -> None: ...
def start_scheduler(build: Callable[[], list[Backend]], interval: int,
                    stop_event: threading.Event, status: BackupStatus) -> Scheduler: ...

# assets/model.py, assets/writer.py (G1)
@dataclass(frozen=True)
class GitSettings:
    url: str
    branch: str
    auth: Literal["token", "gitlab"] = "token"
    token: str | None = field(default=None, repr=False)
@dataclass(frozen=True)
class AssetConfig:
    name: str
    backend: BackendKind
    git: GitSettings | None = None
@dataclass(frozen=True)
class ConfigSnapshot:
    path: Path
    assets: tuple[AssetConfig, ...]
    interval: int
    digest: str                                   # SHA-256 of the file read
def read_snapshot(path: Path) -> ConfigSnapshot: ...
def add_asset(snapshot: ConfigSnapshot, asset: AssetConfig) -> ConfigSnapshot: ...
def remove_asset(snapshot: ConfigSnapshot, name: str) -> ConfigSnapshot: ...
class ConfigChanged(Exception): ...

# wiring.py (G1, G2)
def build_backends(snapshot: ConfigSnapshot, status: BackupStatus) -> list[Backend]: ...

# login/types.py, login/store.py (G2)
ProviderName = Literal["keycloak", "gitlab", "s3keys"]
ConnectionState = Literal["connected", "not_connected", "expired"]
@dataclass(frozen=True)
class Connection:
    provider: ProviderName
    subject: str
    obtained_at: datetime
    secret: dict[str, str] = field(repr=False)    # refresh_token, or key pair
def load(provider: ProviderName) -> Connection | None: ...
def save(connection: Connection) -> None: ...
def delete(provider: ProviderName) -> None: ...
def locked(provider: ProviderName) -> ContextManager[None]: ...

# login/sts.py, login/credentials.py (G3, G5); no caching across rounds
@dataclass(frozen=True)
class S3Credentials:
    access_key: str
    secret_key: str = field(repr=False)
    session_token: str | None = field(default=None, repr=False)
def s3_credentials() -> S3Credentials: ...          # raises LoginError
def gitlab_access_token() -> str: ...               # G5; raises LoginError

# login/flow.py, login/session.py (G3)
def start(provider: ProviderName, username: str, poll_id: str | None = None) -> str: ...
def complete(provider: ProviderName, code: str, state: str, username: str) -> Connection: ...
def verify(access_token: str) -> str: ...           # username; raises SessionError
```

The scheduler calls `s3_credentials()` and `gitlab_access_token()` at
most once per round and passes the result to the backends of that
round.

## Testing strategy

| Level | Scope | Tooling |
| :--- | :--- | :--- |
| Unit | Every module | pytest; fakes on `PATH` or `http.server` |
| Contract | `/storage/status` byte-identity for today's configs | Snapshot test, written in G1 before the refactor |
| Integration | S3 round trip, versions, restore, deletion brake | SeaweedFS container (G2) |
| Integration | Keycloak connect, STS, isolation, revoke, audience | Keycloak and SeaweedFS containers; password grant in tests only (G3) |
| Integration | GitLab connection | GitLab container, or skipped without one (G5) |
| Browser | Page flows, CSRF, headers, expired session | Playwright against the test compose (G6) |
| Compose | Network exposure, front door, `NET_RAW` | `test-compositions.yml` (G1, G2, G3, G7) |

Integration tests skip when Docker is absent.

## Risks

| Risk | Mitigation |
| :--- | :--- |
| SeaweedFS OIDC, policy variables, audience checks or lifecycle on versioned buckets differ from the wiki | G0 spike before G2; if lifecycle is not enforced, the provisioning job runs a scheduled cleanup that deletes only noncurrent versions older than N days (`ListObjectVersions` + `DeleteObjectVersion` with the admin identity), never current objects |
| GitLab release lacks PKCE for public applications, or the ID token on refresh | G0 spike; fallback `GITLAB_OWNER_CHECK = "confirm"` |
| nginx `auth_request` adds latency to every request, or blocks workspaces when Keycloak is down | 30-second cache; Oathkeeper already depends on Keycloak |
| Users added without re-running provisioning get a redirect-URI error | Operator docs; provisioning reads the same user list as compose |
| Two `uvicorn` servers in one loop misbehave on shutdown | G3 test for the 8-second shutdown with both |
| Live reload races a running round | Reload only between rounds; G1 test |
| Comments lost when the writer rewrites a hand-edited file | Warning before the first save; documented trade-off |
