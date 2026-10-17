# Build Script Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close issue #87 and every item in `docs/PENDING_ISSUES.md` that is
still true on `main` (d27a3c2), then reduce that file to what remains.

**Architecture:** Small, independent fixes in the startup scripts, the admin
install script, nginx config, the Dockerfile, the dev Traefik compose files
and CI. `configure_nginx.py` stops shelling out to `sed` and does the
substitution in Python. The admin CLI is installed into its own venv under
`/opt` and linked into `/usr/local/bin`, the way Jupyter already is.

**Tech Stack:** Bash, Python 3 (stdlib only for startup), nginx, Docker,
Docker Compose, GitHub Actions, pip/venv, poetry-core.

**Spec:** Issue #87 ("Potential Vulnerabilities in Build Scripts") and
`docs/PENDING_ISSUES.md`.

## Triage of the source items against `main`

| Source item | Status on `main` | Task |
| --- | --- | --- |
| #87.1 / PI 1: `configure_nginx.py` concatenates env vars into `shell=True` | Still true (every variable, `MAIN_USER` included) | 1 |
| #87.2 / PI 3, 4, 10: `workspace-admin` PATH, pipx as root | Still true. pipx installs as root into `$HOME/.local/bin` (`HOME=/home/kasm-default-profile` at build time); `pipx ensurepath` + `source ~/.bashrc` only affect the build shell | 2 |
| PI 9: Poetry version vs lock-version 2.1 | Still true. `poetry install` creates a venv that is deleted with `/opt/admin`; only `poetry build` matters, and pip can do that build | 2 |
| PI 11: no `apt-get update` in `install_admin.sh` | Still true (relies on lists left by `image_wegovy.sh` and `install_nginx.sh`) | 2 |
| #87.3 / PI 8: `/services` location regex not anchored | Still true, `nginx.conf:50` | 3 |
| #87.9: no `HEALTHCHECK` | Still true | 3 |
| CI: the connectivity check never runs for `compose.yml` and `compose.traefik.yml` | Found while reading the workflow; not in the sources. See Task 3 | 3 |
| #87.4: `custom_startup.sh` no binary check, silent failed restarts | Still true | 4 |
| PI 2: admin README says `/services` | Still true, `workspaces/src/admin/README.md:307`; `DOCUMENTATION.md:23` and `:700` show unprefixed URLs too | 5 |
| PI 5: `--path-prefix` default `dtaas-user` | Decided: keep. `README.md:279` and `test_main.py:51` already document it; the container always passes `--path-prefix "$MAIN_USER"` | 5 (docs), 7 |
| PI 6, 12: prefix substitution read from env | **Resolved**: `load_services()` takes no prefix and the template has no placeholder | 7 (remove) |
| PI 7: VNC endpoint docs | Body already removed; only the summary line remains | 7 (remove) |
| #87.5 / PI 29: Docker socket mount undocumented | Still true, `compose.traefik.yml:25` and `compose.traefik.secure.yml:32` (the TLS and `ci/` files already mount it `:ro`) | 6 |
| #87.6 / PI 32, 35: `myservice` labels, unused `frontend` network | Still true in `compose.traefik.yml` (labels also in `compose.traefik.secure.yml:27`) | 6 |
| #87.7 / PI 36: compose lint passes on zero files | Still true, `docker-lint.yml` | 6 |
| #87.8 / PI 37: README claims markdownlint runs in CI | Still true, no workflow runs it; 423 findings today | 6 |

## Global Constraints

- All paths are under `workspaces/`; `CLAUDE.md` names some files without
  that prefix (`startup/…`, `install/…`). Do not move files.
- Pin every new action by commit SHA with a version comment, like the existing
  workflows. Pin every new tool version.
- Startup Python stays stdlib-only (it runs with the image's system
  `python3` before any venv).
- Lint gates that must stay green: `hadolint` (error threshold),
  `shellcheck` (`.shellcheckrc`, severity warning), `flake8` + `pylint` on
  every `.py` outside `workspaces/src/admin` (`.pylintrc` has
  `fail-under=10.0`, so new files must score 10/10), `yamllint .`,
  `poetry run pytest` and `poetry run pylint src/admin tests` in
  `workspaces/src/admin`, and the `test-compositions` workflow.
- No behaviour change for the published image's routes: `/`, `/lab`,
  `/tools/vscode`, `/tools/vnc`, `/{MAIN_USER}/services`,
  `/{MAIN_USER}/storage/status`, `/ping`.
- Docker is needed for Tasks 2, 3, 4 and 6. `docker compose` reads
  `workspaces/test/dtaas/.env` if present; the examples below assume
  `USERNAME1` is unset, so `MAIN_USER=user1`.

## Review Focus

1. `MAIN_USER` holding `@`, `'`, `;`, space, `/` or a leading `-`: startup
   must refuse with a message naming the variable, before writing anything.
   Pinned in Task 1.
2. A port variable unset or non-numeric (`NO_VNC_PORT` comes from the Kasm
   base image, not our Dockerfile): fail loudly naming the variable. Pinned
   in Task 1.
3. `nginx.conf` keeps both `{WORKSPACE_BASE_URL_DECODED}` and
   `{WORKSPACE_BASE_URL_ENCODED}`; both get `"/" + MAIN_USER`. With the
   charset Task 1 allows, `quote()`/`unquote()` were identity functions.
4. `/user1/servicesXYZ`, `/user1/SERVICES` and `/user1/services/` must not
   reach the admin app; `/user1/services` must. Pinned in Task 3's curl
   checks.
5. Traefik's Docker provider skips a container whose health status is not
   `healthy`, and `starting` counts as not healthy. The `HEALTHCHECK` must
   therefore pass quickly, and CI must actually exercise a route through
   Traefik. Pinned in Task 3.

---

### Task 1: `configure_nginx.py` without a shell

**Files:**

- Modify: `workspaces/src/startup/configure_nginx.py` (full rewrite)
- Create: `workspaces/test/startup/test_configure_nginx.py`
- Modify: `.github/workflows/lint-scripts.yml` (`python-lint` job: add a
  pytest step)

**Context:** `dtaas_shim.sh:40-41` copies the template to
`/etc/nginx/nginx.conf` as root and runs this script under `set -e`, so a
non-zero exit stops the container with the message in `docker logs`. The
template is the only input; the environment is the only configuration.

**Interface** (everything a caller or test needs):

- `class ConfigError(ValueError)`: the message names the offending variable.
- `render(template: str, env: Mapping[str, str]) -> str`: returns the
  template with every placeholder replaced, or raises `ConfigError`. Pure.
- `main(path: str = NGINX_FILE, env: Mapping[str, str] | None = None) -> int`:
  reads `path`, renders with `env` (default `os.environ`), writes back,
  returns `0`. On `ConfigError`: prints `[ERROR] <message>` to stderr,
  returns `1`, writes nothing. Guarded by
  `if __name__ == "__main__": sys.exit(main())`.

Rules `render` enforces:

- `MAIN_USER` required and matching `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,31}$`.
  This is shadow's own username charset minus the Samba `$` suffix, so no
  name that `usermod --login` in `dtaas_shim.sh` accepts today is turned
  away; it also contains nothing that is special inside the nginx regexes or
  quoted strings the value lands in.
- `JUPYTER_SERVER_PORT`, `CODE_SERVER_PORT`, `NO_VNC_PORT`,
  `ADMIN_SERVER_PORT` required, digits only, `1`–`65535`. No defaults: the
  Dockerfile sets three and Kasm sets `NO_VNC_PORT`, so a missing one is a
  real misconfiguration.
- Placeholders: `{MAIN_USER}`, `{JUPYTER_SERVER_PORT}`, `{CODE_SERVER_PORT}`,
  `{VNC_PORT}` (from `NO_VNC_PORT`; keep the existing comment explaining the
  name), `{ADMIN_SERVER_PORT}`, and `{WORKSPACE_BASE_URL_DECODED}` and
  `{WORKSPACE_BASE_URL_ENCODED}`, both `"/" + MAIN_USER`. Drop `urllib`.

Tests, in `workspaces/test/startup/test_configure_nginx.py`. Load the module
by path with `importlib.util.spec_from_file_location` (`startup/` is not a
package). `TEMPLATE = Path(__file__).parents[2] / "src/startup/nginx.conf"`
and `VALID_ENV` with `MAIN_USER="user1"` and ports `8090`, `8054`, `6901`,
`8091`:

1. `test_render_fills_the_real_template`: `render(TEMPLATE.read_text(),
   VALID_ENV)` contains `"/user1/services"` and `"127.0.0.1:6901"` and
   matches no `\{[A-Z_]+\}`.
2. `test_missing_variable_is_named`, parametrized over the five variable
   names: deleting one from `VALID_ENV` raises `ConfigError` whose message
   contains that name.
3. `test_unsafe_main_user_rejected`: `"a@b"`, `"a'b"`, `"a;rm -rf /"`,
   `"a b"`, `"a/b"`, `"-a"`, `"ü"`, 33 `a`s → `ConfigError` naming
   `MAIN_USER`. `test_valid_main_user_accepted`: `"User.1"`, `"a-b_c"`
   render.
4. `test_bad_port_rejected`: `"80a"`, `"0"`, `"65536"`, `""` in
   `ADMIN_SERVER_PORT` → `ConfigError` naming it.
5. `test_main_rewrites_file`: copy the template to `tmp_path`;
   `main(str(file), VALID_ENV) == 0`; the file matches no `\{[A-Z_]+\}`.
6. `test_main_refuses_without_writing`: same file, `MAIN_USER="a;b"`;
   returns `1`, file bytes unchanged, `capsys` stderr contains `MAIN_USER`.

- [ ] **Step 1: Work the six tests one at a time.** Write the test, run
  `python3 -m pytest workspaces/test/startup -q`, watch it fail for the
  right reason (`ImportError`/`AttributeError` first, then an assertion),
  write only what makes it pass, repeat. Test 1 drives the rewrite itself:
  remove `subprocess`, read the template, replace, no shell.

- [ ] **Step 2: Run** `flake8 --max-line-length=127
  workspaces/src/startup/configure_nginx.py workspaces/test/startup` and
  `pylint --rcfile=.pylintrc workspaces/src/startup/configure_nginx.py
  workspaces/test/startup/test_configure_nginx.py`. Expected: no findings,
  score 10.00.

- [ ] **Step 3: Add a step** `Run startup unit tests` to the `python-lint`
  job in `lint-scripts.yml` after `Install linting tools`:
  `pip install pytest==9.1.1` then `python -m pytest workspaces/test/startup
  -q`. Run `yamllint .github/workflows/lint-scripts.yml`.

- [ ] **Step 4: Commit** `fix: substitute nginx placeholders without a
  shell (#87)`.

### Task 2: System-wide admin CLI install

**Files:**

- Modify: `workspaces/src/install/admin/install_admin.sh`
- Modify: `workspaces/src/admin/pyproject.toml` (`[build-system]` only)

**Decision:** install like Jupyter (`install_jupyter.sh:11-15`): a venv
under `/opt`, the entry point symlinked into `/usr/local/bin`, which is on
the build `PATH` captured into `.docker_set_envs`. This drops pipx and
Poetry from the image, and with them PI 3, 4, 9 and 10.

```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-venv \
    python-is-python3
python3 -m venv /opt/workspace-admin
/opt/workspace-admin/bin/pip install --no-cache-dir "${ADMIN_DIR}"
ln -s /opt/workspace-admin/bin/workspace-admin /usr/local/bin/workspace-admin
rm -rf /var/lib/apt/lists/* "${ADMIN_DIR}"
```

- `pip install <dir>` builds the wheel through the `poetry-core` backend
  declared in `pyproject.toml`; `poetry.lock` is not consulted, which is
  already the case today (the wheel's own ranges decide). Pin the backend:
  `requires = ["poetry-core>=2.0.0,<3.0.0"]`.
- `python3-venv` is needed in the `minimal` variant, where nothing else
  installs it. Keep `python-is-python3`: users have `python` on the desktop
  today.
- `${ADMIN_DIR}` (`/dockerstartup/admin`) exists only to be built from;
  remove it at the end. `/opt/workspace-admin` is created with umask 022, so
  uid 1000 can read it; Step 3 checks.
- Keep the `command -v workspace-admin` and `workspace-admin --version`
  checks. The `~/.cache` cleanup lines go (`--no-cache-dir`).

- [ ] **Step 1: Record today's state.** Build
  `docker build --build-arg INSTALLATION=minimal -t ws-before -f
  workspaces/Dockerfile.ubuntu.noble.xfce workspaces`, then
  `docker run --rm --entrypoint bash ws-before -c 'command -v
  workspace-admin; readlink -f "$(command -v workspace-admin)"; echo
  "$PATH"'`. Record where the binary lives (expected under
  `/home/kasm-default-profile/.local`) and whether `PATH` contains it;
  put the answer in the commit message, since the issue asks why it works.
- [ ] **Step 2: Edit `install_admin.sh`** per the decision and pin
  `poetry-core`; `shellcheck workspaces/src/install/admin/install_admin.sh`
  clean. In `workspaces/src/admin`, `poetry run pytest -q` still passes.
- [ ] **Step 3: Rebuild** as `ws-after`; repeat Step 1's command. Expected:
  `/usr/local/bin/workspace-admin` resolving to
  `/opt/workspace-admin/bin/workspace-admin`. Then
  `docker run --rm --user 1000 --entrypoint workspace-admin ws-after
  --version` prints the version.
- [ ] **Step 4: Smoke test** with `docker compose -f
  workspaces/test/dtaas/compose.yml up -d --build`, wait 30 s,
  `curl -fsS http://localhost/user1/services`. Expected: the JSON catalogue.
  Also `docker compose … logs workspace | grep -c "Restarting Admin"`
  is `0`.
- [ ] **Step 5: Commit** `fix: install workspace-admin system-wide (#87)`.

### Task 3: nginx route anchoring, image healthcheck, CI connectivity check

**Files:**

- Modify: `workspaces/src/startup/nginx.conf:50`
- Modify: `workspaces/Dockerfile.ubuntu.noble.xfce` (`deploy` stage)
- Modify: `.github/actions/test-composition/action.yml`
- Modify: `.github/workflows/test-compositions.yml` (matrix)

**Decisions:**

- Replace `location ~* "^{WORKSPACE_BASE_URL_DECODED}/services"` with
  `location = "{WORKSPACE_BASE_URL_DECODED}/services"`, the form
  `storage/status` already uses. The admin app serves exactly that path.
- `HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3
  CMD curl -fsS http://localhost:8080/ping || exit 1`, placed in the
  `deploy` stage after `EXPOSE`. `curl` is installed by `install_nginx.sh`
  in both variants (the dex CI test already runs `curl` inside the minimal
  `user1` container). The 10 s interval is deliberate: Docker runs the first
  probe one interval after start, and until it passes Traefik answers 404
  for the container's routes (Review Focus 5).
- CI gap: `test-composition/action.yml` guards the connectivity step with
  `if: ${{ inputs.dex_test == 'false' }}`, but the first four matrix entries
  pass `dex_test` as `${{ matrix.composition.dex_test }}`, which is the empty
  string, not `false`, so the step is skipped; the same applies to every
  `== 'false'` guard. The matrix endpoint `http://localhost/user/services`
  would also fail if it ran (`MAIN_USER` is `user1`). Fix both: change every
  `== 'false'` guard to `!= 'true'`, and set
  `connectivity_endpoint: "http://localhost/user1/services"` and
  `connectivity_expected_response_code: "200"` on the `compose.yml` and
  `compose.traefik.yml` entries. `check-service-health` looks only at
  `State == running`, and no compose file has `depends_on: condition:
  service_healthy` on a workspace, so the healthcheck itself blocks nothing.

- [ ] **Step 1:** With the Task 2 single-user stack running, record
  `curl -s -o /dev/null -w '%{http_code}\n' http://localhost<path>` for
  `/user1/services`, `/user1/servicesXYZ`, `/user1/SERVICES`,
  `/user1/services/`. Expected today: `200` for all four (the regex
  matches them all).
- [ ] **Step 2:** Edit `nginx.conf`, the Dockerfile, the action and the
  workflow. `hadolint workspaces/Dockerfile.ubuntu.noble.xfce` and
  `yamllint .github` clean.
- [ ] **Step 3:** Rebuild and rerun Step 1. Expected: `/user1/services` →
  `200` with the JSON body; the other three are not `200` from the admin
  app (they fall through to the Jupyter and redirect locations; record the
  codes).
- [ ] **Step 4:** `docker inspect --format '{{.State.Health.Status}}'
  workspace` is `healthy` within 20 s of `up`.
- [ ] **Step 5:** Bring up `compose.traefik.yml`; time how long
  `curl -s -o /dev/null -w '%{http_code}' http://localhost/user1/services`
  takes to turn `200` after `up -d`. Expected: at most about 15 s. Record
  it in the commit message.
- [ ] **Step 6:** In the PR's CI run, open the `compose.yml` and
  `compose.traefik.yml` jobs and confirm `Test service endpoint` ran and
  passed (it was skipped before).
- [ ] **Step 7: Commit** `fix: anchor services route, add HEALTHCHECK,
  run the CI connectivity check (#87)`.

### Task 4: Fail-loud `custom_startup.sh`

**Files:**

- Modify: `workspaces/src/startup/custom_startup.sh`

**Context:** Kasm's `vnc_startup.sh` starts this script in the background
with its output on the container's stdout, and relaunches it every 3 s
whenever it exits (`kasm_fixes.sh` fixes the typo that used to break that
loop). So an `exit 1` here is loud: the error line repeats every 3 s in
`docker logs` and the container stays up. An `exit` inside an `||` list does
not trigger the `ERR` trap, so `cleanup`'s `exit 0` does not get in the way.

**Decisions:**

- `function require_binary { command -v "$1" >/dev/null || { echo "[ERROR]
  required binary '$1' not found on PATH" >&2; exit 1; }; }`. Before anything
  starts: `nginx` and `workspace-admin` always, `jupyter` unless
  `JUPYTER_DISABLED=1`, `code-server` unless `VSCODE_DISABLED=1`.
- Restart reporting: after each `start_*` in the restart loop, `sleep 1`
  and `kill -0` the new PID; if it is gone, `echo "[ERROR] ${process} failed
  to restart; retrying in 3 s" >&2`. No give-up counter: Kasm's own loop
  retries forever, and a permanently broken service should stay visible.

- [ ] **Step 1:** In a running Task 3 container, `docker exec workspace
  sudo rm /usr/local/bin/workspace-admin` then `docker exec workspace pkill
  -f workspace-admin`. Record `docker logs`: expected today, `[INFO]
  Restarting Admin server` every 3 s and nothing else.
- [ ] **Step 2:** Implement; `shellcheck
  workspaces/src/startup/custom_startup.sh` clean.
- [ ] **Step 3:** Rebuild, repeat Step 1. Expected: `[ERROR] admin failed
  to restart; retrying in 3 s` every 3 s; `curl -fsS
  http://localhost/user1/tools/vnc/` still answers (other services up).
- [ ] **Step 4:** Build once more with `RUN rm
  /usr/local/bin/workspace-admin` appended locally to the `setup` stage
  (not committed). Expected in `docker logs`: `[ERROR] required binary
  'workspace-admin' not found on PATH` followed by Kasm's `The custom
  startup script exited.`, repeating every 3 s, and `curl
  http://localhost/ping` refused (nginx was never started).
- [ ] **Step 5: Commit** `fix: fail loudly on missing binaries and failed
  restarts (#87)`.

### Task 5: Admin docs match the routes nginx serves

**Files:**

- Modify: `workspaces/src/admin/README.md:307`
- Modify: `workspaces/src/admin/DOCUMENTATION.md` (`:23`, `:700`, and any
  other example that reaches `/services`, `/health` or `/storage/status`
  without a prefix). Since split into `workspaces/src/admin/DEVELOPER.md`
  and `docs/workspace-admin/STORAGE.md`

**Decision (made):** the `--path-prefix` default stays `dtaas-user`;
`main.py` and `test_main.py` are untouched. Only the prose changes:

- README line 307: nginx serves `/{MAIN_USER}/services` (e.g.
  `/user1/services`) and `/{MAIN_USER}/storage/status`; no other admin
  route is proxied.
- DOCUMENTATION.md: every example URL carries the prefix (`dtaas-user`
  locally, `{MAIN_USER}` through nginx). Port 8080 examples go through
  nginx and therefore always have the prefix; port 8091 examples reach the
  app directly. Remove "(or `/services` without prefix)".

- [ ] **Step 1:** `grep -n "localhost:8080/services\|/services\` without"
  workspaces/src/admin/*.md` lists the stale lines. Edit them. Expected
  afterwards: the grep prints nothing.
- [ ] **Step 2:** `npx --yes markdownlint-cli2@0.18.1
  workspaces/src/admin/README.md workspaces/src/admin/DOCUMENTATION.md`
  reports no new findings (both files have a handful of pre-existing ones
  that Task 6 clears).
- [ ] **Step 3: Commit** `docs: describe the admin routes nginx actually
  serves`.

### Task 6: Traefik dev compose and CI lint gaps

**Files:**

- Modify: `workspaces/test/dtaas/compose.traefik.yml`,
  `workspaces/test/dtaas/compose.traefik.secure.yml`
- Modify: `workspaces/test/dtaas/TRAEFIK.md`
- Modify: `.github/workflows/docker-lint.yml`
- Modify: `.github/workflows/lint-scripts.yml` (new `markdown-lint` job)
- Create: `.markdownlintignore`
- Modify: `README.md:231-233` and the Markdown files the new job flags

**Decisions:**

- Remove the two `myservice` labels (and the then-empty `labels:` key) from
  the `traefik` service in both compose files.
- In `compose.traefik.yml` only, remove `frontend` from the `traefik`
  service and from `networks:`; nothing else in that file attaches to it.
  The secure files attach `keycloak`, `client` and others to their own
  `dtaas-frontend`; leave them. Update `TRAEFIK.md:19` ("Two Docker
  networks") to one.
- Mount the socket `:ro` in both files (the TLS and `ci/` files already
  do), with a comment above pointing to TRAEFIK.md. Add a "Docker socket"
  subsection to TRAEFIK.md: the mount is root-equivalent access to the
  host's Docker daemon even read-only; these files are dev-only; for
  production use a socket proxy such as `tecnativa/docker-socket-proxy`
  exposing only `CONTAINERS=1`, or Traefik's file provider.
- Compose lint in `docker-lint.yml`: `mapfile -t files < <(find . -name
  "compose*.yaml" -o -name "compose*.yml")`; if empty, `echo "ERROR: no
  compose files found" >&2; exit 1`; loop over `"${files[@]}"`.
- Markdown job in `lint-scripts.yml` using the action
  `DavidAnson/markdownlint-cli2-action`, pinned to commit
  `21c1be1b93ad9ed58fa840aacc3f279cde2a72ff` (v24.2.0, add the version as a
  trailing comment) with `globs: "**/*.md"`. It reads `.markdownlint.yaml`
  as is. Today the repo has 423 findings, of which 350 sit in six files. Put those
  in `.markdownlintignore`: `docs/PENDING_ISSUES.md` (Task 7 rewrites it
  and removes it from the list), `docs/POTENTIAL_IMPROVEMENTS.md`,
  `docs/CHANGELOG.md`, `workspaces/test/dtaas/MOTIVATION.md`,
  `.github/copilot-instructions.md`, `docs/superpowers/**`. Fix the
  remaining ~75 findings (mostly `MD013`, `MD032`, `MD031`, `MD022`) in the
  other files in this task. In `README.md:231`, say the check runs in CI
  and that `.markdownlintignore` lists the files it skips.

- [ ] **Step 1:** `docker compose -f workspaces/test/dtaas/<file>
  --env-file workspaces/test/dtaas/config/.env.example config --quiet`
  for both compose files, before and after the edit → all succeed.
- [ ] **Step 2:** Bring `compose.traefik.yml` up; `curl -fsS
  http://localhost/user1/services` returns JSON; `docker network ls` shows
  no `dtaas-frontend`.
- [ ] **Step 3:** Run the new compose-lint snippet in an empty directory →
  exits 1 with the error; in the repo root → lints every file and exits 0.
- [ ] **Step 4:** `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` → `0
  error(s)`; `yamllint .` clean.
- [ ] **Step 5: Commit** `chore: tidy dev Traefik compose and close CI
  lint gaps (#87)`.

### Task 7: Update the backlog documents

**Files:**

- Modify: `docs/PENDING_ISSUES.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `.markdownlintignore` (remove `docs/PENDING_ISSUES.md`)
- Modify: `CLAUDE.md` (only the stale paths this work touched:
  `startup/…` → `workspaces/src/startup/…`, `install/…` →
  `workspaces/src/install/…`, `Dockerfile` →
  `workspaces/Dockerfile.ubuntu.noble.xfce`, `TRAEFIK.md` location)

- [ ] **Step 1:** Remove from `PENDING_ISSUES.md` every item fixed by Tasks
  1–6, the already resolved PI 6, 7 and 12, and PI 5 (retired as intended
  behaviour, now documented: the default is `dtaas-user`, the container
  always passes `MAIN_USER`). Update the total and the priority summary. If
  nothing is left, replace the body with one line saying so and pointing to
  issue #87.
- [ ] **Step 2:** Add an "Unreleased" CHANGELOG entry listing the fixes in
  the file's existing format, including the Traefik routing delay from Task
  3 Step 5 as a "Changed" line.
- [ ] **Step 3:** `npx --yes markdownlint-cli2@0.18.1 "**/*.md"` → `0
  error(s)` with `docs/PENDING_ISSUES.md` no longer ignored.
- [ ] **Step 4: Commit** `docs: retire resolved pending issues (#87)`.

## Final verification (before PR)

- `hadolint`, `shellcheck` on all changed scripts, `flake8`/`pylint` on
  `configure_nginx.py` and its test, `yamllint .`, markdownlint, admin
  `pytest` and `pylint`, startup `pytest`.
- Full image build (`INSTALLATION=full`) and minimal build.
- Single-user compose and `compose.traefik.yml`: every route listed under
  Global Constraints answers as before; container reports `healthy`.
- PR body closes #87 with a checklist mirroring the issue's success
  criteria, and states the one behaviour change: routes through Traefik
  answer about 10 s after container start instead of immediately.
