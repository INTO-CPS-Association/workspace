# Run Keycloak Script Tests

This guide explains how to run the integration test script in [scripts/keycloak/test/test_keycloak_scripts.ps1](scripts/keycloak/test/test_keycloak_scripts.ps1).

## What The Test Verifies

The script starts a temporary Keycloak container, creates a test realm and client, runs the Keycloak configuration scripts, and verifies:

1. Shared scope dtaas-shared exists.
2. Required mappers exist: profile, groups, groups_owner, sub_legacy.
3. Shared scope is assigned to the dtaas-workspace client default scopes.

## Prerequisites

1. Docker is installed and running.
2. Windows PowerShell 5.1 or later is available.
3. Internet access is available for first-time Docker image pulls.

## Run The Integration Test

From repository root [.](/):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\keycloak\test\test_keycloak_scripts.ps1
```

Expected end summary:

- Results: N passed, 0 failed

## Important Credential Note

1. The test script no longer uses a hardcoded password.
2. If `-AdminPass` is not supplied, it generates a random ephemeral password per run.
3. Never commit real admin credentials to source control.

## Useful Test Options

Keep test container for debugging:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\keycloak\test\test_keycloak_scripts.ps1 -KeepContainer
```

Use a different host port:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\keycloak\test\test_keycloak_scripts.ps1 -Port 18090
```

Increase startup timeout:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\keycloak\test\test_keycloak_scripts.ps1 -TimeoutSeconds 300
```

Override admin user and password explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\keycloak\test\test_keycloak_scripts.ps1 -AdminUser "admin" -AdminPass "replace-this-value"
```

## Running configure_keycloak_rest.sh Directly

Run the supported Keycloak configuration script directly from repository root:

```powershell
docker run --rm `
	-v "${PWD}/scripts/keycloak:/scripts" `
	-e KEYCLOAK_BASE_URL="http://host.docker.internal:18080" `
	-e KEYCLOAK_CONTEXT_PATH="/" `
	-e KEYCLOAK_REALM="dtaas" `
	-e KEYCLOAK_CLIENT_ID="dtaas-workspace" `
	-e KEYCLOAK_ADMIN="admin" `
	-e KEYCLOAK_ADMIN_PASSWORD="replace-this-value" `
	debian:bookworm-slim `
	sh -c "apt-get -qq update && apt-get -qq install -y curl jq >/dev/null 2>&1 && sh /scripts/configure_keycloak_rest.sh"
```

## Troubleshooting

If startup fails:

1. Ensure Docker daemon is running.
2. Ensure selected host port is free.
3. Re-run with -KeepContainer and inspect logs:

```powershell
docker logs <container-name>
```
