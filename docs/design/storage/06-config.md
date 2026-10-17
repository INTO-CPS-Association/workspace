# 6. Configuration: `config.toml`, `/config` page and CLI

Part of the [storage design](README.md). Three ways to change the same
configuration, all going through one validator and one writer in the
new package `admin/assets/` (the existing `admin/config/` folder holds
data files and is left alone).

## `config.toml`

Location unchanged: `$PERSISTENT_DIR/.config/workspace-admin/config.toml`,
mode `0600`. Deployment-wide settings are not in it; they come from
the environment ([connect](03-connect-backends.md#deployment-wide-settings)).

```toml
SYNC_INTERVAL_SECONDS = 300

# S3 asset: no other keys. Folder assets/models -> s3://<bucket>/<user>/models/
[assets.models]
BACKUP_BACKEND = "s3"

# Git asset using the GitLab connection.
[assets.thesis]
BACKUP_BACKEND = "git"
GIT_REPO_URL = "https://gitlab.example.org/alice/thesis.git"
GIT_REPO_BRANCH = "main"
GIT_AUTH = "gitlab"

# Git asset with a pasted token, exactly as today.
[assets.private]
GIT_REPO_URL = "https://gitlab.com/alice/private.git"
GIT_REPO_BRANCH = "main"
GIT_REPO_TOKEN = "glpat-..."
```

### Rules

| Key | Rule |
| :--- | :--- |
| Section name | `^[a-z0-9]{1,63}$`; unique; no special names |
| `BACKUP_BACKEND` | `git` (default) or `s3` |
| `GIT_AUTH` | `token` (default) or `gitlab` |
| `GIT_REPO_URL`, `GIT_REPO_BRANCH` | Required for git; URL HTTPS; with `GIT_AUTH = "gitlab"` its host must be `GITLAB_URL`'s; existing branch checks |
| `GIT_REPO_TOKEN` | Required when `GIT_AUTH = "token"`, refused otherwise; placeholders refused |
| S3 sections | No keys besides `BACKUP_BACKEND` |

Validation is per section. A section that fails is reported by name
and skipped; the others run. An S3 section while `S3_ENDPOINT` is
unset is not an error in the file: the asset reports
`s3_not_configured` each round.

### Compatibility

- `[assets.private]` and `[assets.common]` files written for today's
  version load with the same meaning: no `BACKUP_BACKEND` means git,
  no `GIT_AUTH` means the pasted token.
- **Change:** today's loader reads only `private` and `common` and
  ignores every other `[assets.*]` section. From G1 on, other sections
  are read. A valid one starts being backed up; an invalid one (for
  example `[assets.my-data]`) is logged and skipped, never stopping
  the others. The release notes say so.

### Writing safely

`admin/assets/writer.py` serves page and CLI:

1. `read_snapshot(path)` returns the parsed assets, the interval and
   the file's SHA-256 together (`ConfigSnapshot`).
2. Apply the change in memory.
3. Validate the whole result with the loader's code.
4. Refuse with `config_changed` if the file's SHA-256 differs from the
   snapshot's.
5. Write to a temporary file in the same folder, `fsync`, `0600`,
   rename over the original.
6. Ask the scheduler to reload.

The writer emits TOML itself (flat sections, strings and integers), so
no TOML-writing dependency is added. **Trade-off:** comments in a
hand-edited file are lost on the first page or CLI save. The page and
CLI warn before the first such save; hand-editing remains supported.

### Live reload

The scheduler reloads when the writer asks, and when the file's
modification time changes (checked each round), so hand edits apply
without restart. Reload waits for the current round, rebuilds the
backends, clones new git assets, and keeps the status of assets that
still exist. A file that cannot be parsed at all is logged and the
previous configuration keeps running.

## `/config` page

Served at `/<user>/config` through nginx, which gains `location`
blocks for `/config`, `/config/` and the internal `/_auth`. Protected
as in the [threat model](04-threat-model.md#protection-layers-for-the-config-page-and-control-socket).

### Layout

1. **Connections**: Keycloak, GitLab, S3 keys (each only when
   configured). Each shows "Connected as `<name>` since `<date>`",
   "Not connected" or "Expired", with Connect, Reconnect or
   Disconnect.
2. **Assets**: name, backend, connection used, last success, last
   error. Row actions: Remove, and Allow deletions when the asset
   reports `s3_delete_limit`.
3. **Add asset**: name; backend (git or S3, only those configured);
   for git: URL, branch, and authentication (GitLab connection when
   the URL is on `GITLAB_URL`, otherwise a write-only token field).

When a JSON call returns 401 because the session expired, the page
shows "Session expired" with a Reload button; reloading goes through
Oathkeeper's login and back.

### Routes

| Method and path | Purpose |
| :--- | :--- |
| `GET /config` | Static HTML |
| `GET /config/app.js` | The page's only script |
| `GET /config/api/state` | Assets, connections, status, CSRF token |
| `POST /config/api/assets` | Add an asset |
| `POST /config/api/assets/<name>/remove` | Remove an asset |
| `POST /config/api/assets/<name>/allow-delete` | Lift the deletion brake for one round |
| `POST /config/api/connect/<provider>` | Start a login; returns the authorize URL |
| `GET /config/callback/<provider>` | OAuth callback |
| `POST /config/api/confirm/<provider>` | Confirm the GitLab account (`confirm` mode) |
| `POST /config/api/disconnect/<provider>` | Disconnect |
| `POST /config/api/s3keys` | Store a static key pair |

Bodies are JSON, so no form-parsing dependency is needed.

## CLI

`workspace-admin` gains subcommands. With none, it serves as today.

```text
workspace-admin asset list
workspace-admin asset add models --backend s3
workspace-admin asset add thesis --backend git \
    --url https://gitlab.example.org/alice/thesis.git --branch main --auth gitlab
workspace-admin asset remove models
workspace-admin asset allow-delete models
workspace-admin connect keycloak | gitlab
workspace-admin connect s3keys            # prompts; never takes secrets as arguments
workspace-admin disconnect keycloak | gitlab | s3keys
workspace-admin status
```

### Control routes

The CLI talks to the running service over a Unix socket at
`/tmp/workspace-admin-<uid>/control.sock`. The service creates the
directory with mode `0700`, refuses to start if it exists with another
owner or mode, removes a stale socket, binds the socket itself and
hands it to `uvicorn`. The directory's mode is the authentication.
Asset routes mirror the page's under `/control/assets`; login routes
are in [Login core](05-login-core.md#control-routes-unix-socket-only).

The service runs two `uvicorn` servers in one event loop: TCP on
`127.0.0.1:${ADMIN_SERVER_PORT}` for nginx, and the socket for the
CLI. `main.py` changes its `--host` default to `127.0.0.1`, and
`custom_startup.sh` stops passing `--host 0.0.0.0`.

### Logging in from the CLI: options considered

| Option | Works with the browser outside the container | Needs | Verdict |
| :--- | :--- | :--- | :--- |
| CLI starts a login, the user's browser completes it on the workspace callback | Yes | A Keycloak session for the callback | **Chosen** (G4) |
| Device flow: short code, approve anywhere | Yes | Provider support; no callback | Later (G8), for deployments without Keycloak sessions |
| Loopback redirect to `127.0.0.1:<port>` | No: the browser cannot reach the container | | Rejected |
| User pastes the code shown on a callback page into the CLI | Yes | An extra copy step; same callback | Rejected: no gain over the chosen flow |
| CLI writes token files directly after its own login | Yes | Duplicate OAuth code; races token rotation | Rejected |

With the chosen flow, `connect keycloak` prints:

```text
Open this link in the browser you use for DTaaS:
  https://<server>/auth/realms/dtaas/protocol/openid-connect/auth?...
Waiting for approval (10 minutes, Ctrl-C to cancel)...
Connected as user1.
```

### When the service is not running

`asset list`, `asset add` and `asset remove` fall back to the writer
directly, so the change applies at next start. `connect`,
`disconnect`, `allow-delete` and `status` need the running service and
say so.

### Scripting

`asset add` takes every value as a flag and does not prompt with
`--yes`. Secrets are read from standard input or a prompt, never from
arguments, so they stay out of shell history and process listings.
