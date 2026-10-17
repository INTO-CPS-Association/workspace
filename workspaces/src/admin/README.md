# Admin Service

A small HTTP service that runs inside every workspace container. It does
two things:

- tells the DTaaS frontend which services the workspace offers, as JSON
- backs up the workspace's `assets` folders to git repositories on a
  timer, so the user never runs a git command

This page is for people who use a workspace or run one. Developers of the
service should read [DEVELOPER.md](DEVELOPER.md). The git backup is
described in full in
[docs/workspace-admin/STORAGE.md](../../../docs/workspace-admin/STORAGE.md).

## URLs

The service listens on port 8091 inside the container (`ADMIN_SERVER_PORT`)
and is started with the workspace's `MAIN_USER` as its path prefix. nginx
forwards exactly two of its routes:

| URL | Returns |
| --- | --- |
| `/{MAIN_USER}/services` | The list of workspace services |
| `/{MAIN_USER}/storage/status` | How the last git backups went |

Both are exact matches. No other route of the service is reachable through
nginx or, in a multi-user deployment, through Traefik. With
`MAIN_USER=user1` and the container started with `-p 8080:8080`:

```bash
curl http://localhost:8080/user1/services
curl http://localhost:8080/user1/storage/status
```

The bundled compose files publish the workspace on port 80, directly or
behind Traefik, so there it is `http://localhost/user1/services`.

## The service list

`/{MAIN_USER}/services` returns one entry per service:

```json
{
  "desktop": {
    "name": "Desktop",
    "description": "Virtual Desktop Environment",
    "endpoint": "tools/vnc"
  },
  "vscode": {
    "name": "VS Code",
    "description": "VS Code IDE",
    "endpoint": "tools/vscode"
  },
  "notebook": {
    "name": "Jupyter Notebook",
    "description": "Jupyter Notebook",
    "endpoint": ""
  },
  "lab": {
    "name": "Jupyter Lab",
    "description": "Jupyter Lab IDE",
    "endpoint": "lab"
  }
}
```

Each `endpoint` is relative to the workspace's base URL, `/{MAIN_USER}/`.
An empty endpoint is the base URL itself. The list is fixed when the image
is built; it does not change with what is running.

## Turning on the git backup

The backup is off until you give it a repository. It takes one restart.

1. **Start the workspace once.** On its first start the service creates
   `/workspace/.config/workspace-admin/config.toml` from a template and
   logs:

   ```text
   WARNING:  Created /workspace/.config/workspace-admin/config.toml; fill in your repositories and restart the workspace
   ```

   Nothing is cloned yet.

2. **Prepare a repository.** On GitLab (or another git host over HTTPS),
   create the repository with at least one commit on the branch you will
   use (tick *Initialize repository with a README*). Create an access
   token with the `read_repository` and `write_repository` scopes.

3. **Fill in the file.** `/workspace` is the host directory mounted into
   the container (`files/<username>` with the bundled compose files), so
   you can edit the file from the host or from inside the workspace. The
   `.config` folder is hidden; show hidden files to see it. Replace the
   example values:

   ```toml
   SYNC_INTERVAL_SECONDS = 300

   [assets.private]
   GIT_REPO_URL = "https://gitlab.com/you/my-workspace.git"
   GIT_REPO_BRANCH = "main"
   GIT_REPO_TOKEN = "glpat-..."
   ```

   `private` is your own repository. A second section, `[assets.common]`,
   can back up files shared between users; leave it commented out if you
   do not need it. The example values from the template are refused, so
   an unedited file never contacts anyone.

4. **Restart the container.** The repository is cloned into
   `/workspace/assets/private` (or `assets/common`), and from then on every
   300 seconds (`SYNC_INTERVAL_SECONDS`) the service commits what changed,
   merges what changed on the remote, and pushes. Files you edit in
   Jupyter, VS Code or the desktop reach the remote within one interval.

The file holds your token. It is created readable by you only, and its
folder carries a `.gitignore` so it is never committed by accident. Do not
move it inside `assets/`.

## Reading the backup status

```bash
curl http://localhost:8080/user1/storage/status
```

```json
{
  "enabled": true,
  "repositories": {
    "private": {
      "last_attempt": "2026-10-17T12:05:00+00:00",
      "last_success": "2026-10-17T12:05:00+00:00",
      "last_error": null
    }
  }
}
```

- `enabled: false` with no repositories means the backup is not running:
  there is no usable `config.toml`, nothing has been cloned, or the first
  clone is still in progress after a start
- every field is `null` until the first backup, one interval after start
- `last_error` stays after a later success; if `last_success` is newer
  than `last_error.at`, the problem is gone
- `last_error.kind` is one of a fixed set of words, such as
  `auth_failed`; see the
  [kinds table](../../../docs/workspace-admin/STORAGE.md#error-kinds)

The status never contains a message, file name, URL or token. The full
reason is in the container log.

## Troubleshooting

Read the container log first: `docker compose logs workspace` (or
`docker logs <container>`). Lines from the backup look like
`INFO:     Git backup config file: /workspace/.config/workspace-admin/config.toml`.

| What you see | What it means | What to do |
| --- | --- | --- |
| `... config.toml not found; git backup is disabled` | No file at the logged path | Check the path; create the file or restart to have it created |
| `Created /workspace/.config/...; fill in your repositories and restart` | The file was just made from the template | Fill it in, restart |
| `... is still the placeholder from config.toml.example` | An example value is still in the file | Replace it, restart |
| `Cannot clone git assets: ...` or `Cannot start git sync: ...` | The file cannot be used; the rest of the line names the key | Fix the file, restart |
| `... GIT_REPO_TOKEN was rejected ...` | The remote refused the token | Check the token and its scopes, restart |
| `Failed to clone repository ...` | The remote, branch or network is wrong | Fix it, restart; a failed clone is only retried on the next start |
| `last_error.kind` is `wrong_branch`, `detached_head`, `operation_in_progress`, `unresolved_conflicts` or `conflict_markers` | You are in the middle of using git in `assets/<name>`; the backup waits | Finish what you started; see [Conflicts](../../../docs/workspace-admin/STORAGE.md#conflicts-what-is-automatic-and-what-is-manual) |
| `last_error.kind` is `index_locked` | Another git command was running | Usually nothing; the next interval tries again |

Changes to `config.toml` take effect on the next restart; there is no
reload. If one repository fails, the other is still backed up and the rest
of the workspace is unaffected.
