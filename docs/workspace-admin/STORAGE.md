# Git Backup of the Workspace (Storage)

The workspace admin service backs the workspace's `assets` folders up to
git repositories. On startup it clones each configured repository into
`$PERSISTENT_DIR/assets/<name>`; from then on, every `SYNC_INTERVAL_SECONDS`
it commits what the user changed, merges what changed on the remote, and
pushes. The user never runs a git command, and the outcome is served by
`/storage/status`.

This page describes the feature in full. For the short version see the
[admin service README](../../workspaces/src/admin/README.md); for the
code, [DEVELOPER.md](../../workspaces/src/admin/DEVELOPER.md). Everything
below is implemented in `workspaces/src/admin/src/admin/git/`.

## The config file

### Where it is

The service always reads one file:

```text
$PERSISTENT_DIR/.config/workspace-admin/config.toml
```

When `PERSISTENT_DIR` is unset, the home directory is the root instead.
The directory the service is started from never matters. The absolute
path is logged on every start:

```text
INFO:     Git backup config file: /workspace/.config/workspace-admin/config.toml
```

| Where the service runs | Root | Config file |
| --- | --- | --- |
| Workspace container | `/workspace` (`PERSISTENT_DIR` in the Dockerfile) | `/workspace/.config/workspace-admin/config.toml` |
| Locally, Linux or macOS | `~` | `~/.config/workspace-admin/config.toml` |
| Locally, Windows | `%USERPROFILE%` | `%USERPROFILE%\.config\workspace-admin\config.toml` |

### Created from the template

The Dockerfile copies `workspaces/src/templates/config.toml.example` into
the image and points `WORKSPACE_CONFIG_TEMPLATE` at the copy
(`$STARTUPDIR/templates/config.toml`). On every start, before anything is
cloned, `provision.py` checks for the config file:

- **Missing, template set** (the image): the directory is created, a
  `.gitignore` holding `*` is written next to the file (mode `0644`), and
  the template is copied into place with mode `0600`, readable by its owner
  only. The log says `WARNING:  Created <path>; fill in your repositories
  and restart the workspace`, and this start clones nothing: the file only
  holds placeholders
- **Missing, template unset** (outside the image): nothing is created and
  the backup is off: `INFO:     <path> not found; git backup is disabled`
- **Present**: it is never overwritten. The `.gitignore` is still added if
  the directory lacks one, so a repository the user creates further up
  never commits the token
- **Cannot be created**: `ERROR:    Could not create <path> from
  <template>: <reason>`, and the backup stays off

### Keys

This is the template, and the whole of the format:

```toml
# Seconds between two backups, from 1 to 86400 (one day). Optional:
# without it the backup runs every 300 seconds. Keep it above the
# [assets] sections, or TOML reads it as part of the section before it.
SYNC_INTERVAL_SECONDS = 300

# Git repository configuration. The section name decides where each
# repository's files appear: /workspace/assets/<name>.

[assets.private]
GIT_REPO_URL = "https://gitlab.com/username/repository.git"
GIT_REPO_BRANCH = "main"
# HTTP token for authentication
GIT_REPO_TOKEN = "gitlab-api-token"

# Uncomment to also back up files shared between users.
# [assets.common]
# GIT_REPO_URL = "https://gitlab.com/username/repository.git"
# GIT_REPO_BRANCH = "main"
# # HTTP token for authentication
# GIT_REPO_TOKEN = "gitlab-api-token"
```

| Key | Required | Value |
| --- | --- | --- |
| `SYNC_INTERVAL_SECONDS` | No | Whole number of seconds between two backups, 1 to 86400. Default 300. Top level, above the first `[assets]` section |
| `[assets.private]` | One of the two | The user's own repository |
| `[assets.common]` | One of the two | A repository shared between users |
| `GIT_REPO_URL` | In each section | `https://` URL of the remote, with a host, without spaces or control characters and without `user:token@` |
| `GIT_REPO_BRANCH` | In each section | The one branch that is cloned and kept in sync. Must not start with `-` and must pass `git check-ref-format --branch` unchanged (so no shorthands such as `@{-1}`) |
| `GIT_REPO_TOKEN` | In each section | Access token, sent as the HTTP Basic password with the fixed username `oauth2`. On GitLab it needs the `read_repository` and `write_repository` scopes |

The file is TOML, so every text value is quoted. Only the two section
names are recognised, because a name becomes part of two paths; an
`[assets]` table holding only other names is an error, not an empty
backup. The three keys of a section must be present, be quoted strings,
and not be blank.

`SYNC_INTERVAL_SECONDS` is the only lenient key. A value that is not a
whole number (`300.0`, `"300"`, `true`), or is outside 1 to 86400, is
reported and the default is used, so the backup still runs:

```text
WARNING:  /workspace/.config/workspace-admin/config.toml: 'SYNC_INTERVAL_SECONDS' must be between 1 and 86400 seconds, got 0; using the default of 300 seconds
```

A key written below a section header belongs to that section in TOML, so
the interval appended at the end of the file lands in the last `[assets]`
section, where it has no effect. That is reported too:

```text
WARNING:  /workspace/.config/workspace-admin/config.toml: 'SYNC_INTERVAL_SECONDS' is in [assets.common], where it has no effect; move it to the top level, above every [assets] section
```

The `--sync-interval` command-line option overrides the file, accepts the
same range, and refuses anything else at startup. The image does not pass
it, so there the file decides. The upper limit keeps the wait well below
what Python's `threading` accepts (`threading.TIMEOUT_MAX` is about 49
days on Windows; past it the wait raises and would end the sync thread).

### Values that are refused

Loading the file raises `ConfigError`, whose message names the file, the
section and the key, when:

- the file cannot be read or is not valid TOML
- there is no `[assets]` section, or it holds neither `private` nor
  `common`, or `[assets.<name>]` is not a table
- a required key is missing, not a string, or blank
- a value is still a placeholder from the template. Exactly these strings
  are refused: `https://gitlab.com/username/repository.git`,
  `https://gitlab.com/username/private-repo.git`,
  `https://gitlab.com/username/common-repo.git` for the URL, and
  `gitlab-api-token`, `gitlab-access-token` for the token. An unedited
  copy of the template can therefore never send a request anywhere
- `GIT_REPO_URL` is not `https://`, has no host, contains whitespace or a
  control character, or carries a username or token. The URL is left out
  of the message, since it may hold a token
- `GIT_REPO_BRANCH` starts with `-`, or `git check-ref-format --branch`
  rejects it or hands it back changed. If git cannot be run to check, that
  is reported as well
- `[assets.private]` and `[assets.common]` name the same URL and branch.
  Both work trees would push to that branch, each winning every conflict
  against the other
- a work tree contains the config file. Everything in a work tree is
  committed and pushed, which would publish the token

`ConfigError` is logged, as `Cannot clone git assets: <message>` at
startup and `Cannot start git sync: <message>` when the interval is read,
and the backup is off for that start. The HTTP API runs as normal.

### Outside the image

Without `WORKSPACE_CONFIG_TEMPLATE` nothing is created for you. Create the
directory and the file under your home directory (or under
`PERSISTENT_DIR`, if you set it before every start), paste the template,
fill it in, and start `workspace-admin`:

```bash
mkdir -p ~/.config/workspace-admin
touch ~/.config/workspace-admin/config.toml
chmod 600 ~/.config/workspace-admin/config.toml
```

```powershell
New-Item -ItemType Directory -Force "$HOME\.config\workspace-admin"
New-Item -ItemType File "$HOME\.config\workspace-admin\config.toml"
```

The first log line must show the file you made. The repositories are
cloned into `assets/<name>` below the same root. After a change to the
file, stop the service and start it again.

## Paths

Every path follows from the root and the section name; the file holds
none. In the container:

```text
/workspace/                                  # $PERSISTENT_DIR
├── .config/workspace-admin/
│   ├── .gitignore                           # "*", so the token is never committed
│   └── config.toml                          # mode 0600
├── .local/share/workspace-admin/
│   ├── private/                             # git directory of private
│   └── common/                              # git directory of common
└── assets/
    ├── private/                             # work tree of private
    │   └── .git                             # file: "gitdir: /workspace/.local/share/workspace-admin/private"
    └── common/                              # work tree of common
        └── .git                             # file: "gitdir: /workspace/.local/share/workspace-admin/common"
```

The **git directory** holds git's own data: history, objects, refs, the
remote URL. The **work tree** holds the checked-out files the user edits.
They are kept apart with `git clone --separate-git-dir`, so a work tree
contains only a one-line `.git` file pointing at the git directory. Every
git command the user runs in `assets/<name>` finds the git directory
through that file.

Both are below `$PERSISTENT_DIR`, so they survive a container rebuild
with the rest of the user's data.

## Startup: cloning

`main.cli()` calls `start_git_backup()` once, which logs the config path
and returns at once. The work runs on a daemon thread named
`git-bootstrap`, so the HTTP API is up whatever the remotes are doing:

1. The config file is created from the template if missing (see above).
   If it was just created, or is still missing, the thread ends here
2. The file is loaded. On `ConfigError`, `Cannot clone git assets: ...` is
   logged and the thread ends
3. Each repository is cloned, `private` first, then `common`. Each one is
   cloned on its own: a failure in one is logged and the other is still
   cloned
4. If the service is already stopping, the thread ends. Otherwise the file
   is loaded again, `SYNC_INTERVAL_SECONDS` is read (unless
   `--sync-interval` was given), and the sync is started for every
   repository whose git directory holds a clone. A repository that failed
   to clone is not backed up until the next start clones it
5. The thread then waits for the sync thread, so shutdown has one thread
   to wait for

There is no route or command that clones later. After adding or changing
a repository in `config.toml`, restart the service; in the container,
restart the container.

### What a clone does

For each repository, `clone_asset()`:

1. checks whether the git directory already holds a `HEAD` file. If so,
   the repository counts as cloned: `INFO:     Repository 'private'
   already cloned at <git dir>; skipping`. This is every start after the
   first. Only the git directory is checked, not the work tree
2. creates the parent of the git directory and the work tree itself
3. runs, with the per-command options described under
   [Authentication and transport](#authentication-and-transport):

   ```bash
   git -c protocol.allow=never -c protocol.https.allow=always \
       -c credential.helper= -c http.lowSpeedLimit=1 -c http.lowSpeedTime=60 \
       -c 'http.extraHeader=Authorization: Basic <base64 of oauth2:token>' \
       clone --branch <GIT_REPO_BRANCH> --single-branch \
       --separate-git-dir=<git dir> -- <GIT_REPO_URL> <work tree>
   ```

   `--branch` and `--single-branch` fetch only the configured branch;
   `--` stops the URL and the path from being read as options
4. logs `INFO:     Cloned repository 'private' (<url>, branch <branch>)
   into <work tree>`

A clone succeeds when the URL is reachable over HTTPS, the token can read
the repository, the branch exists on the remote (a new repository with no
commits has no branches), and neither directory already exists with files
in it (git refuses with `already exists and is not an empty directory`;
an empty directory is fine).

### When a clone fails

```text
ERROR:    Failed to clone repository 'common' (<url>, branch main) into <work tree>: <git's message>
ERROR:    git clone failed for repository 'common': <git's message>
```

- If the failure looks like rejected credentials, the second line ends
  with `(the configured GIT_REPO_TOKEN was rejected - it may be invalid or
  expired; check config.toml)`. GitLab answers a wrong token and an
  expired one the same way, so the message does not claim to know which.
  The token itself is never logged
- A clone that runs out of time (900 seconds) is logged as
  `ERROR:    Timed out cloning repository 'common' (<url>, branch main):
  git did not finish within 900 seconds and was stopped`
- A failed clone is not retried while the service runs. git cleans up
  after a failed or interrupted clone, so the directories are left empty
  and do not block the next start
- Until something is cloned, `/storage/status` reports
  `"enabled": false`; a wrong token on first start is visible in the log
  only

## The sync cycle

The sync runs on a daemon thread named `git-sync`. The first cycle happens
one interval after the start, not immediately, because the repositories
were just cloned. The log says:

```text
INFO:     Started git sync for 2 repository/repositories every 300 seconds
```

Every interval, each repository goes through `sync_once()` in turn. A
repository that fails is logged and skipped, so one broken remote does
not stop the other from being backed up. The steps, in this order:

1. **Checks before touching anything.** The cycle stops here, with
   nothing changed, when another git process holds `index.lock`, an
   operation is in progress, the wrong branch or no branch is checked
   out, or files are unmerged. See
   [Conflicts](#conflicts-what-is-automatic-and-what-is-manual)
2. **Commit.** `git status --porcelain` decides whether there is anything
   to save; a clean tree logs `No changes in repository 'private'; nothing
   to commit`. Otherwise `git add -A` stages everything, the staged files
   are checked for conflict markers (and unstaged again if any are
   found), and the commit is made with the identity `workspace-admin
   <workspace-admin@localhost>` and the message
   `workspace backup <UTC timestamp>`, for example
   `workspace backup 2026-10-17T12:30:00Z`
3. **Pull.** `git fetch -- origin +refs/heads/<branch>:refs/remotes/origin/<branch>`,
   then `git rev-list --count HEAD..origin/<branch>`. Nothing incoming
   logs `Repository 'private' is already up to date`. Otherwise the branch
   is checked again (the fetch can take minutes, long enough to switch
   branches) and `git merge origin/<branch>` runs. A clean merge logs
   `Merged 3 incoming commit(s) into repository 'private' without
   conflicts`. A conflict is resolved in favour of the workspace, see
   below; any other failure aborts the merge with `git merge --abort` and
   ends the cycle
4. **Push.** `git rev-list --count origin/<branch>..refs/heads/<branch>`
   counts what the remote lacks; zero means no push. Otherwise
   `git push -- origin refs/heads/<branch>:refs/heads/<branch>` and
   `Pushed 1 commit(s) from repository 'private' to branch main`

Committing before merging is deliberate: git refuses to merge over
modified files, so an uncommitted tree would make every pull fail as soon
as the remote had anything to deliver. The push names the branch, not
`HEAD`, so what is counted is exactly what is sent.

Between the steps the cycle checks whether the service is stopping. If
so it ends there with `INFO:     Stopped synchronizing repository
'private' before it could push; the service is stopping`; nothing is
recorded for it, and a commit left unpushed is pushed by the first cycle
after the next start.

After each repository the outcome is recorded: a success, or the kind of
the `SyncError`. Any other exception is logged with its traceback as
`Unexpected error while syncing repository 'private'` and recorded as
`unexpected`; the thread carries on, because an exception escaping it
would end every further backup while the service kept serving requests.

## Conflicts: what is automatic and what is manual

Most of the time the backup needs nothing from the user. A few situations
cannot be decided safely by a program; there the backup stops for that
repository, logs why, records the kind in `/storage/status`, and tries
again every interval until a person has sorted it out. Nothing half
finished is ever committed or pushed.

| Situation | Handled by | What the backup does | To get it going again |
| --- | --- | --- | --- |
| Both sides changed the same file | Backup | Keeps the workspace's whole file, merges every other file | Nothing |
| One side changed a file the other deleted | Backup | Keeps the workspace's side: a file changed here is kept, a file deleted here stays deleted | Nothing |
| A merge, rebase, cherry-pick or revert you started is unfinished | You | Waits: no commit, no pull, no push | Finish or abort it |
| Git still lists files as conflicted | You | Waits: no commit, no pull, no push | Fix the files, then `git add` |
| A file holds conflict markers | You | Refuses to commit, unstages again | Remove the markers |
| Another branch, or no branch, is checked out | You | Waits: no commit, no pull, no push | Check out `GIT_REPO_BRANCH` |
| Another git command is running | You | Skips this interval | Usually nothing |

The commands below are run in the work tree, `/workspace/assets/<name>`
in the container. The service can keep running while you work: as long as
your merge is unfinished, the backup waits instead of interfering. If
`git commit` asks who you are, add `-c user.name="Your Name"
-c user.email="you@example.com"` after `git`: the clone stores no
identity, so nothing is written into the repository on your behalf.

### Both sides changed the same file

Automatic. The merge stops on the conflict, `git ls-files --unmerged -z`
lists the files, and for each one `git checkout --ours` takes the
workspace's whole version; no line from the remote is mixed in. The merge
is then concluded with `git commit --no-edit`. The log names the files:

```text
WARNING:  Merge conflict in repository 'common' affecting 1 file(s): notes.md
INFO:     Resolved the conflict in repository 'common' by keeping the local version of: notes.md
```

The remote's version is not lost: it is in the history, in the commit that
was merged in. Files without a conflict get the remote's changes as
normal.

### One side changed a file the other deleted

Automatic, in favour of the workspace. Git keeps the workspace's version
of a conflicted file as stage 2; a file without one was deleted here.

- changed here, deleted on the remote: the file is kept and pushed back
- deleted here, changed on the remote: `git rm` keeps it deleted, and the
  deletion is pushed

The log is the same as above.

### A merge or rebase you started is unfinished

The backup looks for the entries git keeps while an operation is stopped:
`MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `REBASE_HEAD`,
`rebase-merge`, `rebase-apply`. With one present it leaves the repository
alone:

```text
ERROR:    Not synchronizing repository 'common': a git operation is in progress (MERGE_HEAD); finish or abort it first
```

Committing now would conclude your merge for you, conflict and all, and
push it. Either finish what you started, after fixing the conflicted
files and running `git add` on them:

```bash
git commit                  # a merge, cherry-pick or revert
git rebase --continue       # a rebase
```

or give it up, which puts everything back as it was:

```bash
git merge --abort           # or: git rebase --abort, git cherry-pick --abort, git revert --abort
```

The name in brackets says which operation it is. The next interval
synchronizes as normal.

### Git still lists files as conflicted

The same protection applies when `git ls-files --unmerged` reports files
without an operation in progress, for example after a `git stash pop`
that conflicted:

```text
ERROR:    Not synchronizing repository 'common': unresolved conflicts in notes.md
```

Open each file the log names, keep the content you want, and mark it
resolved with `git add notes.md`. The next interval commits and pushes it.

### A file holds conflict markers

A file can be marked resolved while it still contains the lines git
writes around a conflict (`<<<<<<<`, `=======`, `>>>>>>>`). After staging,
the backup runs `git diff --cached --check`, keeps only its
`leftover conflict marker` warnings, and refuses when the staged file
really has a line starting with `<<<<<<<` or `>>>>>>>`:

```text
ERROR:    Not committing in repository 'common': conflict markers left in notes.md
```

Nothing is committed and the files are unstaged again with `git reset`,
so your work tree is as you left it. Open each file the log names: between
`<<<<<<<` and `=======` is one version, between `=======` and `>>>>>>>`
the other. Keep the lines you want and delete the rest, the three marker
lines included. Save the file, or delete it. No git command is needed;
the next interval commits as normal.

A line holding just `=======` is also how Markdown underlines a heading,
so on its own it is committed as normal. A file holding a line that
starts with `<<<<<<<` on purpose, such as notes about git, is refused all
the same.

### Another branch is checked out

The backup commits to, merges into and pushes `GIT_REPO_BRANCH` only.
`git symbolic-ref --quiet HEAD` tells which branch is checked out; when it
is another one, or none at all (a tag, a single commit, a `git bisect`
session), the backup waits:

```text
ERROR:    Not synchronizing repository 'common': 'experiment' is checked out, not 'main'; check out 'main' to resume the backup
ERROR:    Not synchronizing repository 'common': HEAD is detached; check out branch 'main' to resume the backup
```

Without this check the backup commits would land on your branch while the
push sent `GIT_REPO_BRANCH`, so they would never reach the remote. Switch
back, finishing a bisect first:

```bash
git bisect reset      # only during a bisect
git switch main       # the branch in GIT_REPO_BRANCH
```

The check runs again just before the merge, because the fetch can take
long enough for you to switch branches in between.

### Another git command is running

Every git command that changes the staging area first creates
`index.lock` in the git directory and deletes it when done. While the
file is less than an hour old, the backup leaves the repository alone for
that interval:

```text
ERROR:    Not synchronizing repository 'common': another git process holds /workspace/.local/share/workspace-admin/common/index.lock; trying again next cycle
```

Usually there is nothing to do. Note that `git commit` without `-m` holds
the lock for as long as its editor is open.

A git process that is killed, for example when the container stops,
leaves the file behind, and git refuses to run until it is gone. The
backup therefore removes an `index.lock` older than 3600 seconds and goes
ahead:

```text
WARNING:  Removed /workspace/.local/share/workspace-admin/common/index.lock from repository 'common': it was 4000 seconds old, so the git process that created it is gone
```

An hour, rather than minutes, so that a commit editor left open over a
break is not mistaken for a crash. A lock that is old but cannot be
removed, or cannot be inspected, skips the cycle with `index_locked`.

### What the backup does not check

The checks cover the commits the backup makes itself. A commit you make
by hand is pushed as it is, conflict markers included: what goes into it
is your decision.

## Authentication and transport

Every git command that contacts the remote (clone, fetch, push) gets
these one-off `-c` options, and nothing is written into the clone's
`.git/config` or its remote URL:

| Option | Effect |
| --- | --- |
| `protocol.allow=never`, `protocol.https.allow=always` | git refuses every transport except https, even if a non-https URL got past the config check or was edited into `.git/config`. `file://`, `ssh://` and `ext::` (which runs a command by design) are refused |
| `credential.helper=` | Empties the list of credential helpers, so one such as Git Credential Manager cannot prompt. Credentials only ever come from `GIT_REPO_TOKEN` |
| `http.lowSpeedLimit=1`, `http.lowSpeedTime=60` | A transfer that has moved less than 1 byte per second for 60 seconds is abandoned. This does not cover a stall before the connection is up, such as a TLS handshake that never completes; the time limit catches that |
| `http.extraHeader=Authorization: Basic <base64 of oauth2:token>` | HTTP Basic credentials for this one command. HTTP Basic needs a username, but the forge identifies the user by the token alone; `oauth2` is the fixed username GitLab documents |

The commit identity is passed the same way, as `-c user.name=...`
`-c user.email=...` on `git commit` and `git merge`, so a commit the user
makes by hand carries their own identity, not a service account.

Every command that names the branch puts `--` before its positional
arguments and spells the branch out as a full refspec, so a branch value
can never be read as a git option such as `--upload-pack`. Together with
the checks on `GIT_REPO_BRANCH` and `GIT_REPO_URL` when the file is
loaded, that is two layers against a config value reaching git as an
option.

When a clone or push fails, the stderr is checked for git's and GitLab's
own rejection text, matched case-insensitively: `authentication failed`,
`http basic: access denied`, `invalid credentials`, `returned error: 401`,
`returned error: 403`. Bare numbers are deliberately not matched, so an
unrelated `401` in a message is not misread. A match records the kind
`auth_failed`, and when a token is configured the logged message ends
with `(the configured GIT_REPO_TOKEN was rejected - it may be invalid or
expired; check config.toml)`. The token never appears in a log line, an
error message or the status; `RepoConfig` leaves it out of `repr()` too.

## Time limits and prompts

Every git command of the backup goes through `run_git()` in `runner.py`,
so none can wait forever, for a person or for the network:

- **No prompts.** `GIT_TERMINAL_PROMPT=0` stops git asking on a terminal;
  an empty `GIT_ASKPASS` stops it starting an askpass helper, which on
  the desktop or under VS Code could open a dialog nobody answers, and
  also overrides `core.askPass` and `SSH_ASKPASS`. Credential helpers
  ignore both, hence `credential.helper=` above. Standard input is empty
- **Time limits.** Commands that talk to the remote get 900 seconds
  (`REMOTE_TIMEOUT_SECONDS`, generous because a first clone of a large
  repository takes a while); every other command 300 seconds
  (`LOCAL_TIMEOUT_SECONDS`). A command that runs out of time is sent
  `SIGTERM`, so git can clean up (an interrupted clone removes the
  directory it started), and `SIGKILL` 5 seconds later if it is still
  running. On POSIX the command runs in its own process group, so helpers
  it started, such as `git-remote-https`, are stopped with it
- A timed-out clone raises `CloneError`; a timed-out sync step raises
  `SyncError` of kind `git_failed`, and the next cycle tries again. The
  message is `git did not finish within 900 seconds and was stopped`

## Shutdown

When the service stops (SIGTERM or Ctrl+C), the FastAPI lifespan runs
`stop_git_backup()` after the server has stopped. It sets the stop event,
so no further git command or repository is started, and waits up to 8
seconds (`SHUTDOWN_TIMEOUT_SECONDS`, under the 10 seconds `docker stop`
allows) for the command already running:

```text
INFO:     Stopped the git backup
WARNING:  The git backup was still running a git command after 8 seconds; not waiting for it any longer
```

A command still running after that keeps running in its own session
until it finishes or the container ends. Each step of a cycle leaves the
repository consistent, so the next start carries on from there.

In the workspace image, `docker stop` has been observed not to reach the
service at all: Kasm's `vnc_startup.sh` is PID 1 and exits as soon as it
has signalled `custom_startup.sh`, after which the kernel kills every
other process. There the stale `index.lock` handling and git's atomic ref
updates are what protect the repository.

## `/storage/status`

Served by the admin service and, in the container, proxied by nginx at
`/{MAIN_USER}/storage/status` as an exact match.

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

- `enabled` is `false`, with no repositories, while the backup is not
  running: `config.toml` is missing or unusable, nothing has been cloned,
  or the clones are still running after a start
- a repository is listed as soon as the sync starts, with every field
  `null` until its first cycle, one interval later
- `last_error` is kept after a later success; if `last_success` is newer
  than `last_error.at`, the error has cleared
- timestamps are UTC, ISO 8601, to the second
- a cycle cut short by shutdown records nothing

### Error kinds

`last_error.kind` is one of a fixed set of words, chosen where the error
is raised:

| Kind | Meaning |
| --- | --- |
| `auth_failed` | The remote rejected the credentials. Check `GIT_REPO_TOKEN` and its scopes |
| `operation_in_progress` | A merge, rebase, cherry-pick or revert is unfinished |
| `unresolved_conflicts` | Git still lists files as conflicted |
| `conflict_markers` | A file about to be committed holds conflict markers |
| `wrong_branch` | Another branch than `GIT_REPO_BRANCH` is checked out |
| `detached_head` | No branch is checked out, for example during `git bisect` |
| `index_locked` | Another git command was running, or an old `index.lock` could not be inspected or removed |
| `git_failed` | Any other failing or timed-out git command: an unreachable remote, a merge stopped by an untracked file in the way, a lock taken during the cycle |
| `unexpected` | An error that is not a git failure, for example `git` missing from the image |

The response never holds a message, file name, URL, branch or username:
the API has no authentication and listens on every interface, so anyone
who can reach it can read this. The full reason is in the service's log,
next to the same timestamp. The route is read-only; there is no route
that starts a backup.

## Log lines

The service logs like uvicorn: `INFO:     message`, `WARNING:  message`,
`ERROR:    message`. The lines of the backup, in the order they can
appear:

| Line | Level | Meaning |
| --- | --- | --- |
| `Git backup config file: <path>` | INFO | The file the service will read. Logged on every start |
| `Created <path>; fill in your repositories and restart the workspace` | WARNING | The file was just made from the template; nothing cloned this start |
| `Could not create <path> from <template>: <reason>` | ERROR | The template could not be copied; backup off |
| `<path> not found; git backup is disabled` | INFO | No file and no template; backup off |
| `Cannot clone git assets: <file>: <reason>` | ERROR | The file cannot be used; the reason names the section and key |
| `Repository '<name>' already cloned at <git dir>; skipping` | INFO | Every start after the first |
| `Cloned repository '<name>' (<url>, branch <b>) into <work tree>` | INFO | First start |
| `Failed to clone repository '<name>' (...): <git's message>` | ERROR | Followed by `git clone failed for repository '<name>': ...`, with the token hint when it applies |
| `Timed out cloning repository '<name>' (...): git did not finish within 900 seconds and was stopped` | ERROR | Followed by the same `git clone failed` line |
| `No cloned repositories found for <path>; git sync not started` | WARNING | Every clone failed, or none has happened yet |
| `Cannot start git sync: <reason>` | ERROR | The file could not be read again when the interval was needed |
| `<file>: 'SYNC_INTERVAL_SECONDS' <problem>; using the default of 300 seconds` | WARNING | Bad interval; backup runs with 300 |
| `<file>: 'SYNC_INTERVAL_SECONDS' is in [assets.<name>], where it has no effect; ...` | WARNING | Key in the wrong place; backup runs with 300 |
| `Started git sync for <n> repository/repositories every <s> seconds` | INFO | The backup is running |
| `No changes in repository '<name>'; nothing to commit` | INFO | Clean tree this cycle |
| `Committed changes in repository '<name>'` | INFO | A backup commit was made |
| `Repository '<name>' is already up to date` | INFO | Nothing to fetch |
| `Merged <n> incoming commit(s) into repository '<name>' without conflicts` | INFO | Remote changes merged |
| `Merge conflict in repository '<name>' affecting <n> file(s): <files>` | WARNING | Followed by `Resolved the conflict in repository '<name>' by keeping the local version of: <files>` |
| `Pushed <n> commit(s) from repository '<name>' to branch <b>` | INFO | The remote has the workspace's commits |
| `Not synchronizing repository '<name>': ...` | ERROR | The cycle was skipped; the rest of the line says why (see [Conflicts](#conflicts-what-is-automatic-and-what-is-manual)) |
| `Not committing in repository '<name>': conflict markers left in <files>` | ERROR | Commit refused, files unstaged again |
| `Removed <lock> from repository '<name>': it was <n> seconds old, ...` | WARNING | A stale `index.lock` was removed and the cycle went ahead |
| `Failed to <action> for repository '<name>': <reason>` | ERROR | A git command failed or timed out; the kind is `git_failed` or `auth_failed` |
| `Unexpected error while syncing repository '<name>'` | ERROR | With a traceback; kind `unexpected` |
| `Stopped synchronizing repository '<name>' before it could <step>; the service is stopping` | INFO | Shutdown cut the cycle short; nothing recorded |
| `Stopped the git backup` | INFO | Shutdown completed in time |
| `The git backup was still running a git command after 8 seconds; not waiting for it any longer` | WARNING | Shutdown gave up waiting |
| `Unexpected error while starting the git backup` | ERROR | With a traceback; something outside the cases above failed on the bootstrap thread |

## Security notes

- **The token lives in `config.toml` only.** The file is created with
  mode `0600` and a `.gitignore` next to it; a file inside a work tree is
  refused, because everything in a work tree is pushed. The token is sent
  as a per-command header, never written into `.git/config` or the URL,
  never logged, and never served by `/storage/status`
- **Everything in `assets/<name>` is committed and pushed**, including
  anything the user drops there. Secrets do not belong in a work tree.
  Untracked files are added by `git add -A`; a `.gitignore` in the work
  tree is honoured, since it is git that stages
- **`common` is shared.** Every workspace configured with the same
  `common` remote pushes to it, and local files win a conflict, so for a
  file two users change the later push wins per file. The other version
  stays in the history
- **Only https, and only what the file names.** The URL and branch are
  validated when loaded, git itself is told to refuse other transports,
  and positional arguments always follow `--`
- **The API is unauthenticated and read-only.** It binds to every
  interface; nothing in it changes state or reveals more than timestamps
  and error kinds. In the container only two routes are proxied, as exact
  matches
- **An unedited file does nothing.** The template's values are refused,
  and there is no fallback to the template, so a workspace nobody
  configured never contacts a remote
- **No prompts, no hangs.** Every git command runs without a terminal,
  without an askpass or credential helper, with empty stdin and a time
  limit
