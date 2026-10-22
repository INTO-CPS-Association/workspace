# SeaweedFS for workspace backups

S3 storage for the S3 backup scheme
([storage schemes](../../../../docs/design/storage/STORAGE_SCHEMES.md)),
used by `compose.traefik.secure.yml` and `compose.traefik.secure.tls.yml`.

| Service | Does |
| :--- | :--- |
| `seaweedfs` | `weed server -s3` on the `users` network only: no ports, no Traefik labels. S3 and STS at `http://seaweedfs:8333`; data in the `seaweedfs-data` volume |
| `seaweedfs-lifecycle` | One lifecycle pass a day (`S3_LIFECYCLE_INTERVAL_SECONDS`, default 86400). `weed server` stores lifecycle rules but never applies them |

Settings in `config/.env`:

| Variable | Purpose |
| :--- | :--- |
| `S3_ADMIN_ACCESS_KEY`, `S3_ADMIN_SECRET_KEY` | Operator identity: bucket, versioning, lifecycle, restore. Never given to a workspace |
| `S3_SIGNING_KEY` | Signs STS sessions and guards the filer's IAM service; at least 32 characters |

`iam.json` trusts storage passes from login-relay
(`http://login-relay:8080`, audience `workspace-backup`) for the role
`arn:aws:iam::role/WorkspaceBackup`. That role reaches only
`dtaas-backup/<preferred_username>/*` and cannot delete versions or
change versioning, lifecycle or bucket policy
([threat model](../../../../docs/design/storage/THREAT_MODEL.md#storage-side-hardening)).

## Spike

`spike/` holds the S1 and S2 checks (findings in
[tasks](../../../../docs/tasks/102-s3-backup.md#spike-findings)). The
spike container stands in for login-relay, so do not start the real
login-relay alongside it. Its own project name keeps `down -v` away
from any running `dtaas` stack. From `workspaces/test/dtaas`:

```bash
compose="docker compose -p seaweedfs-spike -f compose.traefik.secure.yml \
  -f seaweedfs/spike/spike.overlay.yml --env-file config/.env"
$compose up -d --wait seaweedfs
$compose run --rm --use-aliases spike main           # S1, 64 checks
$compose restart seaweedfs
$compose run --rm --use-aliases spike after-restart  # persistence
$compose run --rm --entrypoint bash spike s2_rclone_flags.sh  # S2
# Lifecycle: age two versions, let the first pass of the sidecar run
$compose run --rm --entrypoint python spike lifecycle_probe.py prepare
$compose up -d seaweedfs-lifecycle && sleep 20
$compose run --rm --entrypoint python spike lifecycle_probe.py verify
$compose down -v
```
