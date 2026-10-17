# Storage design

Design of workspace backup to git and S3 storage, with connections
managed through Keycloak and GitLab logins. Issue
[workspace#102](https://github.com/INTO-CPS-Association/workspace/issues/102).

| # | Document | Read it for |
| :--- | :--- | :--- |
| 1 | [Storage schemes](01-storage-schemes.md) | Assets, git and S3 backup, SeaweedFS storage, cloud S3 |
| 2 | [OIDC security](02-oidc-security.md) | Tokens, browser PKCE and device flows, Keycloak and GitLab differences |
| 3 | [Connect storage backends](03-connect-backends.md) | Connections, credentials per round, life cycle, status |
| 4 | [Threat model and protection](04-threat-model.md) | Actors, boundaries, threats, controls, residual risks |
| 5 | [Login core](05-login-core.md) | Modules, sequences and errors of the login code |
| 6 | [Configuration](06-config.md) | `config.toml`, the `/config` page and the CLI |
| 7 | [Complete system design](07-system-design.md) | Components, deployment, behaviour, decisions |
| 8 | [Effect of Route B](08-route-b-impact.md) | Proposal: GitLab or Keycloak per deployment, `login-relay` as token bridge (pending acceptance) |

Related:

- [Feature roadmap](../../FEATURE_ROADMAP.md): build order.
- [Auth design, Route B](../auth/login-relay-gitlab.md): `login-relay`
  and Oathkeeper in place of `traefik-forward-auth`.
- [Spec](../../specs/102-s3-backup.md),
  [plan](../../plans/102-s3-backup.md) and
  [tasks](../../tasks/102-s3-backup.md).
- Git backup as built: `workspaces/src/admin/README.md` and
  `DOCUMENTATION.md`.
