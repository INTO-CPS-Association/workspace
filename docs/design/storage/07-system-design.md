# 7. Complete system design

Part of the [storage design](README.md). Puts documents 1 to 6
together: context, components, deployment, behaviour, quality
requirements and decisions.

## System context

```mermaid
flowchart LR
    user([Workspace user]) -- browser --> traefik[Traefik + Oathkeeper]
    op([Operator]) -- compose, consoles --> host[(DTaaS host)]
    traefik --> ws[Workspace container per user]
    ws -- OAuth, userinfo --> kc[Keycloak]
    ws -- OAuth, git HTTPS --> gl[GitLab]
    ws -- STS, S3 --> s3[(SeaweedFS or cloud S3)]
    s3 -. signing keys .-> kc
```

## Components inside a workspace

```mermaid
flowchart TB
    subgraph admin[workspace-admin process]
        public[Public routes<br/>/services /health /storage/status]
        cfg[Config routes<br/>/config, callbacks, /_auth]
        ctl[Control routes<br/>/control/*]
        wiring[Composition root<br/>admin/wiring.py]
        login[Login core<br/>admin/login]
        assets[Asset config<br/>admin/assets]
        sched[Scheduler and status<br/>admin/backup]
        gitb[Git backend<br/>admin/git]
        s3b[S3 backend<br/>admin/s3]
    end
    nginx[nginx :8080] -->|auth_request /_auth| cfg
    nginx -->|127.0.0.1:8091| public & cfg
    cli[workspace-admin CLI] -->|Unix socket| ctl
    cfg & ctl --> login & assets
    cfg & ctl -->|request_reload| sched
    sched -->|rebuild| wiring
    wiring --> gitb & s3b
    sched --> gitb & s3b
    gitb & s3b -->|credentials| login
    public --> sched
    gitb --> git[[git]]
    s3b --> rclone[[rclone]]
```

| Package | Owns | Imports |
| :--- | :--- | :--- |
| `admin/backup` | `Backend` protocol, scheduler, status, error kinds | standard library only |
| `admin/login` | Connections, flows, session check, STS | standard library only |
| `admin/assets` | Parse, validate, write `config.toml` | `backup` (kinds) |
| `admin/git` | Git backend: existing clone, sync, auth | `backup`, `login` |
| `admin/s3` | S3 backend, `rclone` runner, error mapping | `backup`, `login` |
| `admin/wiring.py` | Builds backends from asset config; the only module that knows every backend | `assets`, `git`, `s3`, `backup` |
| `admin/web` | Config, callback, `/_auth` and control routes; static page | `login`, `assets`, `backup`, `wiring` |
| `admin/cli` | Subcommands; socket client; offline writer fallback | `assets` |
| `admin/api.py` | Public routes (unchanged contract) | `backup` |

The dependency graph has no cycle: `backup` and `login` sit at the
bottom; only `wiring` and `web` see everything.

## Files in a workspace

```text
$PERSISTENT_DIR/
├── assets/<name>/                         backed-up folders
├── .config/workspace-admin/               never backed up
│   ├── config.toml                        0600
│   ├── .gitignore                         "*"
│   └── tokens/{keycloak,gitlab,s3keys}.json   0600
└── .local/share/workspace-admin/<name>/   git directories
/tmp/workspace-admin-<uid>/control.sock    directory 0700
```

## Deployment (Docker Compose)

| Service | Networks | Ports | Changes |
| :--- | :--- | :--- | :--- |
| traefik, oathkeeper, login-relay | as today | as today | none |
| keycloak | as today | as today | `workspace-backup` client: public, PKCE, consent, audience mapper, per-user redirect URIs |
| `user<N>` workspaces | `users` | none | `cap_drop: [NET_RAW]`; S3, OIDC and GitLab variables; admin on `127.0.0.1`; nginx `auth_request` |
| `seaweedfs` | `users` only | none | `weed server -s3`, `/data` volume, `s3.json`, `iam.json` |
| `storage-provision` | `users` | none | One-shot, profile `provision`: bucket, versioning, lifecycle, IAM files, Keycloak client, GitLab application redirect URIs |

Admin credentials for SeaweedFS, Keycloak and GitLab exist only in
`storage-provision` and the operator's `.env`; workspaces never get
them. On Kubernetes the same pieces become a StatefulSet, a Job and a
ConfigMap; that port is out of scope here.

## Behaviour

### Startup

1. Parse arguments. Create the control-socket directory and bind the
   socket; start TCP on `127.0.0.1`.
2. Create `config.toml` from the template if missing (existing
   `provision.py`). Operators may pre-seed assets in the template.
3. Load and validate the asset configuration; `wiring` builds one
   backend per valid asset.
4. On a background thread, `prepare` each backend (clone, bucket
   check) and start the scheduler. HTTP never waits for this.

### A sync round

1. Reload first if `config.toml` changed or a reload was requested.
2. If any S3 asset exists, call `s3_credentials()` once; if any git
   asset uses GitLab, call `gitlab_access_token()` once. A failure
   marks those assets with the mapped status kind and skips them;
   other assets continue.
3. Sync each asset; record success or the error kind.
4. Stop between assets when the service is stopping.

### Shutdown

Set the stop event; a running `git` or `rclone` ends within the
existing 8-second limit; pending logins are dropped; the socket is
removed.

## Quality requirements

| Quality | Requirement | How |
| :--- | :--- | :--- |
| Security | Neighbouring workspaces cannot reach a workspace's tools or admin | nginx `auth_request`, `127.0.0.1`, socket directory `0700` |
| Security | No secret in logs, argv, status or page | Write-only fields; credentials via environment for `rclone` and git |
| Security | Configuration changes need the owner's session or socket | Session check, CSRF, socket |
| Reliability | One failing asset or connection never stops others | Per-asset errors and per-section validation |
| Reliability | No data loss from an empty or unmounted folder, or mass deletion | Empty-source refusal, `S3_MAX_DELETE` |
| Availability | Backups run while the page is unused | Credentials refreshed per round |
| Responsiveness | Sync never blocks HTTP | Background thread, as today |
| Portability | Cloud S3 by configuration | Standard protocols only |
| Maintainability | New files under 250 lines, functions under 25; files already over 250 do not grow; pylint 9.0+ | Small modules per concern |
| Dependencies | No new Python runtime dependency; one pinned `rclone` | Standard library HTTP, XML, locking |

## Decisions

| # | Decision | Reason |
| :--- | :--- | :--- |
| D1 | `rclone` for S3 | Sync, excludes and version restore built in |
| D2 | One backend per asset | Git pulls and S3 mirrors conflict on one folder |
| D3 | Free asset names `^[a-z0-9]{1,63}$`, no special names | Sharing is a server policy, not a client choice |
| D4 | Add and remove only | Renaming moves data across folders, prefixes and repositories |
| D5 | One bucket, prefix per user | Bucket limits and cost in clouds; prefix policies suffice |
| D6 | Keycloak connection for S3, GitLab connection for git | Central revocation, short-lived credentials |
| D7 | GitLab connection alongside pasted tokens | Non-breaking; other git hosts keep working |
| D8 | Browser login with PKCE first; device flow later | Reuses the DTaaS session; works on any GitLab |
| D9 | Admin on `127.0.0.1`; CLI on a Unix socket in a `0700` directory | Nothing that changes configuration is reachable without the owner's session or account |
| D10 | Session check through `userinfo`, also for nginx | No crypto dependency; catches logged-out sessions; closes the front door |
| D11 | Hand-editable `config.toml` with version check | Page, CLI and editor coexist; comments lost on machine saves |
| D12 | Provisioning in the DTaaS repository | User list, compose and Keycloak live there |
| D13 | Fresh credentials every round | Revocation takes effect next round |
| D14 | Exact per-user redirect URIs, registered by provisioning | Providers do not accept the needed wildcard |
| D15 | `cap_drop: [NET_RAW]` on workspaces | Internal OAuth and STS traffic is plain HTTP |

## Open questions

1. Noncurrent-version retention: is 30 days right for course
   deployments?
2. Keycloak offline-session maximum for DTaaS: 90 or 180 days?
3. Which SeaweedFS and GitLab releases are deployed? Pins follow
   roadmap group G0.
4. Which DTaaS deployment does G7 target, and does it adopt
   Oathkeeper and `login-relay`? See the
   [roadmap](../../FEATURE_ROADMAP.md#groups).
