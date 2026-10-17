# Admin Service: Developer Guide

For people changing the service. What it does and how to use it is in
[README.md](README.md); the git backup is described in
[docs/workspace-admin/STORAGE.md](../../../docs/workspace-admin/STORAGE.md).

## Setup

You need Python 3.12 or newer, git, and [Poetry](https://python-poetry.org/).

```bash
cd workspaces/src/admin
poetry install
```

## Running it

```bash
# Serve the API with the default prefix, dtaas-user
poetry run workspace-admin

# The same, spelled out
poetry run workspace-admin --path-prefix dtaas-user

# Routes at the root, without a prefix
poetry run workspace-admin --path-prefix ""

# Another host and port
poetry run workspace-admin --host 127.0.0.1 --port 9000

# Print the service catalogue as JSON and exit
poetry run workspace-admin --list-services

# Auto-reload on code changes
poetry run workspace-admin --reload

# Back up every 30 seconds, whatever config.toml says
poetry run workspace-admin --sync-interval 30

poetry run workspace-admin --version
poetry run workspace-admin --help
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--host` | `0.0.0.0` | Interface to bind |
| `--port` | `$ADMIN_SERVER_PORT`, else `8091` | Port to bind |
| `--path-prefix` | `$PATH_PREFIX`, else `dtaas-user` | Prefix for every route; `""` for none |
| `--reload` | off | uvicorn auto-reload, for development |
| `--sync-interval` | the config file's value, else 300 | Seconds between backups, 1 to 86400; refused outside that range |
| `--list-services` | | Print the catalogue and exit without serving |
| `--version` | | Print the version from `pyproject.toml` and exit |

The default prefix `dtaas-user` is intended: it matches the default
`MAIN_USER` of the image. The container never relies on it;
`custom_startup.sh` always passes `--path-prefix "$MAIN_USER"`.

On start the service prints a banner with its four URLs, then starts the
git backup on a background thread and serves. Outside the image no config
template is installed, so the backup logs
`<home>/.config/workspace-admin/config.toml not found; git backup is disabled`
and stays off. To run it locally, create that file by hand as described in
[STORAGE.md](../../../docs/workspace-admin/STORAGE.md#outside-the-image).
The API works either way.

## HTTP API

Every route is `GET`, read-only, unauthenticated, and served on every
interface. The prefix is normalised by `normalize_path_prefix()`:
surrounding slashes are stripped and one leading slash is added, so
`dtaas-user`, `/dtaas-user/` and `dtaas-user/` all become `/dtaas-user`;
an empty or all-slash value means no prefix. With a prefix, the unprefixed
paths answer 404. Below, `{p}` is the prefix or nothing.

FastAPI's own `/docs` and `/openapi.json` are at the root, outside the
prefix, as FastAPI serves them by default.

In the image nginx proxies only `/{MAIN_USER}/services` and
`/{MAIN_USER}/storage/status`, as exact matches. `/` and `/health` are
reachable on port 8091 inside the container only.

### `GET {p}/`

Service name, version and the routes it offers. With a prefix, the path
is `/dtaas-user/`; `/dtaas-user` without the slash answers 307 to it.

```json
{
  "service": "Workspace Admin Service",
  "version": "0.2.0",
  "endpoints": {
    "/services": "Get list of available workspace services",
    "/health": "Health check endpoint",
    "/storage/status": "Outcome of the most recent git backups"
  }
}
```

The version is read from the installed distribution's metadata, so
`pyproject.toml` is the only place it is declared. From a source tree that
is not installed it is `0.0.0+unknown`.

### `GET {p}/services`

The service catalogue, read from `config/services_template.json` on every
request. A map of service identifier to `name`, `description` and
`endpoint`; the endpoint is relative to the workspace's base URL, and
empty means that base URL itself. The response for the current template is
shown in [README.md](README.md#the-service-list).

### `GET {p}/health`

```json
{"status": "healthy"}
```

Answers as soon as the process serves, whatever the git backup is doing.
A broken backup must not make an orchestrator restart a workspace, which
is why the backup has its own route.

### `GET {p}/storage/status`

A snapshot of `SyncStatus`:

```json
{
  "enabled": true,
  "repositories": {
    "private": {
      "last_attempt": "2026-10-17T12:05:00+00:00",
      "last_success": "2026-10-17T12:00:00+00:00",
      "last_error": {
        "kind": "auth_failed",
        "at": "2026-10-17T12:05:00+00:00"
      }
    },
    "common": {
      "last_attempt": "2026-10-17T12:05:00+00:00",
      "last_success": "2026-10-17T12:05:00+00:00",
      "last_error": null
    }
  }
}
```

`enabled` is `false` with an empty `repositories` until the scheduler has
repositories to sync. Timestamps are UTC ISO 8601 with second precision,
or `null`. `last_error.kind` is a `SyncErrorKind` value; the full list and
what each one means is in
[STORAGE.md](../../../docs/workspace-admin/STORAGE.md#error-kinds). Only
timestamps and kinds leave the process, never a message. Any method other
than `GET` answers 405.

## Code layout

```text
src/admin/
├── __init__.py
├── api.py                        # FastAPI app factory and HTTP routes
├── services.py                   # Workspace service discovery
├── main.py                       # Command-line entry point
├── config/
│   └── services_template.json    # Service catalogue (data, not code)
└── git/                          # Git backup of workspace directories
    ├── __init__.py
    ├── runner.py                 # Runs one git command without prompts, within a time limit
    ├── config.py                 # config.toml -> RepoConfig
    ├── auth.py                   # Per-command HTTP auth header and failure detection
    ├── clone.py                  # Clones one RepoConfig
    ├── sync.py                   # One cycle for a cloned tree: commit, pull, push
    ├── scheduler.py              # Runs the cycle on a timer, in the background
    ├── status.py                 # Outcome of the last backups, for /storage/status
    ├── provision.py              # Creates a missing config.toml from the template
    └── bootstrap.py              # Wires the above together on startup
```

Dependencies point one way only: `main` → `api` → `services`. `api` owns
the transport and nothing else; the logic behind a route lives in a
sibling module, so each layer is tested on its own. `main` is the startup
sequence: it parses the command line and decides which of the other layers
to run.

The `git` package is layered the same way, `bootstrap` → `scheduler` →
`sync`/`clone` → `auth` → `config` → `runner`:

- `runner.py`: `run_git()` runs every git command of the backup with
  prompts off, empty stdin and a time limit, and stops a command that
  overruns together with the processes it started (`GitTimeoutError`). It
  knows nothing about repositories, so every other module can use it
- `config.py`: `load_config()` reads `config.toml` and returns one
  `RepoConfig` per `[assets.<name>]` section, with both paths resolved
  below the root; `load_sync_interval()` reads `SYNC_INTERVAL_SECONDS`.
  Anything unusable raises `ConfigError`, naming the file, section and key
- `auth.py`: `remote_options()` builds the per-command `-c` options for a
  command that contacts the remote (https only, no credential helper,
  stalled transfers abandoned, the `Authorization` header);
  `is_auth_failure()` recognises a rejected token in git's stderr
- `clone.py`: `clone_asset()` clones one `RepoConfig`, git directory and
  work tree kept apart; `is_cloned()` checks for a `HEAD` file
- `sync.py`: `sync_once()` runs one cycle for a cloned tree: commit, pull,
  push. Local files win a conflict. Refuses to touch a repository the user
  is busy with and raises `SyncError` with a `SyncErrorKind`
- `scheduler.py`: `start_sync_scheduler()` runs `sync_all()` on a daemon
  thread every interval and records each outcome in a `SyncStatus`
- `status.py`: `SyncStatus`, the thread-safe record of last attempt,
  success and error kind per repository
- `provision.py`: `provision_config()` copies the template into place when
  `config.toml` is missing
- `bootstrap.py`: `start_git_backup()`, called once from `main.cli()`,
  provisions, clones and starts the sync on the `git-bootstrap` thread;
  `stop_git_backup()` is run by the FastAPI lifespan on shutdown

Failures in `git/` are logged, never raised to `main`: a broken git
configuration must not stop the HTTP API from starting.

`api.py` imports `SyncStatus` from `git/status.py` and nothing else from
the package, so the HTTP layer depends on the record of outcomes but not
on git itself.

## Tests

```bash
cd workspaces/src/admin
poetry run pytest --cov=admin --cov-report=html --cov-report=term-missing
```

The HTML report lands in `htmlcov/index.html`. The test files mirror the
package, so a change to a module has one obvious test file:

| Test file | Module | Covers |
| --- | --- | --- |
| `tests/unit/test_api.py` | `api.py` | Every route with and without a prefix, prefix normalisation, the version from package metadata, `/storage/status` serving the live status and refusing writes, the shutdown hook running once after the server stops |
| `tests/unit/test_services.py` | `services.py` | Catalogue loading and template integrity |
| `tests/unit/test_main.py` | `main.py` | Flags and their defaults from the environment, `--list-services`, `--version`, `--sync-interval` range-checked, the backup started before serving with the same `SyncStatus` the API reports and stopped by the shutdown hook |
| `tests/unit/test_git_runner.py` | `git/runner.py` | Prompts off, empty stdin, failures returned not raised, overrunning commands stopped (SIGTERM, then SIGKILL, including child processes) |
| `tests/unit/test_git_config.py` | `git/config.py` | One entry per section, paths derived from the section name below the root, old top-level path keys ignored, missing, empty or mistyped keys, no fallback to the template, placeholders refused, shared remote branches refused, config inside a work tree refused, branch names checked with `git check-ref-format` (and a hung check reported), https-only URLs without credentials, `SYNC_INTERVAL_SECONDS` read, defaulted, and misplaced or unusable values falling back with a warning |
| `tests/unit/test_git_auth.py` | `git/auth.py` | Header built or omitted by credentials, https-only options, helpers reset and stalled transfers abandoned, token never in the header text, auth-failure text recognised without matching bare numbers |
| `tests/unit/test_git_clone.py` | `git/clone.py` | Clone, skip when cloned, failure, timeout and its limit, https-only, `--` before the URL, the token-free hint on a rejected token |
| `tests/unit/test_git_sync.py` | `git/sync.py` | Commit, clean tree, in-progress operation, unmerged files and conflict markers refused (Markdown underlines allowed), identity and timestamp, pull up to date, clean merge, whole-file and deletion conflicts, explicit refspecs, https-only, dash-led branch never an option, aborted merges, push when ahead, auth errors, time limits per command, wrong branch and detached `HEAD` (also after the fetch), outgoing commits counted by branch, fresh and stale `index.lock`, stopping between steps |
| `tests/unit/test_git_scheduler.py` | `git/scheduler.py` | Every repository synced, one failure not stopping the others, unexpected errors survived, loop until stopped, outcomes recorded as kinds, nothing recorded for a round cut short |
| `tests/unit/test_git_status.py` | `git/status.py` | Disabled until enabled, timestamps, last error kept after a success, snapshots are copies, concurrent writers |
| `tests/unit/test_git_provision.py` | `git/provision.py` | Created from the template with mode `0600`, never overwritten, `.gitignore` added and kept, nothing without a template, a missing template logged |
| `tests/unit/test_git_bootstrap.py` | `git/bootstrap.py` | Config path below `PERSISTENT_DIR` or home and never the working directory, missing config disables everything, unedited template clones nothing, every section cloned independently, only cloned repositories scheduled, the clone on a background thread, the stop event honoured, the shutdown wait giving up, the interval from the file unless given |
| `tests/integration/test_git_sync_conflicts.py` | `git/sync.py` | Conflict resolution against real git with a local bare repository as the remote: both directions of modify/delete, no remote lines in a conflicted file, other files still merged, the next sync clean |

`tests/helpers/` holds shared code, not tests: `fake_git.py` (`FakeGit`
replaces `run_git()` and answers every command with canned results),
`repo_factory.py` (`make_repo()` builds a `RepoConfig` with only the
fields a test cares about) and `templates.py` (the path of
`config.toml.example`, which only resolves in a source checkout).

## Linting

```bash
cd workspaces/src/admin
poetry run pylint src/admin tests
```

CI (`.github/workflows/workspace-admin.yml`) runs pylint with the
repository's `.pylintrc` and `--fail-under=9.0`, then pytest with
coverage, then `poetry build`. It is triggered by changes under
`workspaces/src/admin/`. Markdown in this directory is linted with the
rest of the repository: `npx markdownlint-cli2 "**/*.md"` from the root.

## Adding a service

Edit `src/admin/config/services_template.json`:

```json
{
  "new_service": {
    "name": "New Service Name",
    "description": "Description of the service",
    "endpoint": "path/to/service"
  }
}
```

The file is read on every request, so no code changes. `endpoint` is
relative to the workspace's base URL and must be a path nginx routes.
`test_services.py` checks that the template is valid JSON, that the four
existing services are there with all three keys, and that every entry has
an `endpoint`.

## How it is installed in the image

`workspaces/Dockerfile.ubuntu.noble.xfce` copies `workspaces/src/admin/`
to `$ADMIN_DIR` (`$STARTUPDIR/admin`) and runs
`workspaces/src/install/admin/install_admin.sh`, which:

1. installs `python3-venv` and `python-is-python3` with apt
2. creates a venv at `/opt/workspace-admin` and runs
   `pip install "$ADMIN_DIR"` in it. pip builds the wheel through the
   `poetry-core` backend named in `pyproject.toml`, so neither Poetry nor
   pipx is in the image. The wheel's dependency ranges decide the versions;
   `poetry.lock` is not consulted
3. links `/opt/workspace-admin/bin/workspace-admin` into `/usr/local/bin`,
   which is on every user's `PATH`
4. checks `workspace-admin --version` and deletes `$ADMIN_DIR` and the
   apt lists

The Dockerfile also copies `workspaces/src/templates/config.toml.example`
to `$WORKSPACE_CONFIG_TEMPLATE` (`$STARTUPDIR/templates/config.toml`) and
sets `PERSISTENT_DIR=/workspace`; both are read by `git/bootstrap.py`.

At runtime `workspaces/src/startup/custom_startup.sh` refuses to start
without the `workspace-admin` binary, then runs
`workspace-admin --host 0.0.0.0 --port "$ADMIN_SERVER_PORT" --path-prefix "$MAIN_USER"`
and restarts it if it dies. nginx is configured by
`workspaces/src/startup/configure_nginx.py` from
`workspaces/src/startup/nginx.conf`, which is where the two proxied routes
are declared.

## Design decisions

These are worth keeping when changing the code.

- **The API is read-only and secret-free.** It has no authentication and
  binds to every interface, so no route changes state (in particular,
  none starts a backup; a "sync now" button needs authentication first)
  and `/storage/status` returns timestamps and error kinds only.
  `RepoStatus` has no field for a message, so one cannot be added by
  accident. Filtering git's output was rejected: git can print something
  new at any time
- **`/storage/status` is not `/health`.** Health checks act on their
  answer, for example by restarting a container. A failing backup is no
  reason to restart a workspace someone is working in
- **The HTTP API never waits for git.** Cloning can take minutes, so
  `start_git_backup()` returns at once and the work happens on the
  `git-bootstrap` thread. Until the clones are done, `/storage/status`
  reports the backup as disabled
- **Failures in `git/` are logged, never raised.** A missing config file
  is a normal state, not an error; a broken one costs the workspace its
  backup but not its API. `sync_all()` catches every exception, because an
  exception escaping the background thread would end the backup silently
  while the service kept answering requests
- **One `SyncStatus`, no global state.** `main.cli()` creates it and hands
  it to both `start_git_backup()` and `create_app()`; the sync thread
  writes, request handlers read, all through one lock
- **Nothing secret is written into a clone.** The token travels as a
  per-command `-c http.extraHeader` and the commit identity as
  `-c user.name/user.email`, so neither lands in `.git/config` or the
  remote URL, and a commit the user makes by hand carries their own
  identity. `RepoConfig.token` is excluded from `repr()`
- **Placeholders are refused and there is no fallback to the template.**
  An earlier version fell back to the bundled example when the user had
  no config file, which made every unconfigured workspace clone and push
  to `https://gitlab.com/username/repository.git`
- **Section names are fixed.** A name becomes part of two paths, so only
  `private` and `common` are accepted, and `[assets]` with only unknown
  names is an error rather than a config that silently backs up nothing
- **Commit before pull.** git refuses to merge over modified files, so an
  uncommitted work tree would make every pull fail as soon as the remote
  had anything to deliver
- **Local files win, per whole file.** `git merge -X ours` was tried first
  and dropped: it resolves per hunk, so remote lines were mixed into a
  "kept" notebook, and it cannot resolve modify/delete at all. The merge is
  now ordinary; on conflict `git ls-files --unmerged -z` names the files
  and `git checkout --ours` or `git rm` takes the workspace's side
- **The backup never concludes something the user started.** Before
  committing it checks for a fresh `index.lock`, an in-progress merge,
  rebase, cherry-pick or revert, another branch or a detached `HEAD`, and
  unmerged files; after staging it checks for conflict markers. Each case
  is a `SyncErrorKind`, so the status says why the backup is waiting
- **Every git command goes through `run_git()`.** Prompts are off, stdin
  is empty, and each command has a time limit, because a git command that
  waits for a person or a stalled network would otherwise hang the backup
  for good
- **A stop is not a failure.** `SyncStopped` is raised between steps when
  the service is stopping; it is logged and nothing is recorded, since
  every step leaves the repository consistent
- **Shutdown waits 8 seconds at most**, under the 10 seconds `docker
  stop` allows before it kills the process

### Known limitations

- A repository that fails to clone is never scheduled, so it does not
  appear in `/storage/status`; a wrong token on first start is visible in
  the log only. A failed clone is retried on the next start, not before
- Only `index.lock` is handled. A stale ref lock such as
  `refs/heads/main.lock` has to be removed by hand
- Brief races remain: a branch switch between the branch check and the
  merge, or a user command taking `index.lock` during a cycle. Either
  fails that one cycle (`git_failed`) and the next interval tries again
- A git command still running when the shutdown wait gives up keeps
  running in its own session until the container ends
- In the image, `docker stop` has been observed not to reach the service:
  Kasm's `vnc_startup.sh` is PID 1 and exits as soon as it has signalled
  `custom_startup.sh`, after which the kernel kills every other process.
  The shutdown path works when the service is signalled directly; in the
  container the stale-lock handling and git's atomic ref updates are what
  protect the repository
