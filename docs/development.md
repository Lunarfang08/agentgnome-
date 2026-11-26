# Development guide

## Environment

`make bootstrap` installs the locked Python/npm dependencies and initializes `.env` with a unique development token. It never prints tokens and preserves custom values. It rotates the former shared development token. `.env` is ignored by Git and written with owner-only permissions on supported systems.

Make targets use the installed environment without synchronizing on every invocation. Rerun bootstrap after changing dependency lockfiles.

### Intel macOS

Cryptography 50.x has no upstream Intel macOS wheel. Install Xcode command-line tools, Rust >=1.83 and a supported OpenSSL. Export `OPENSSL_DIR` to the OpenSSL installation prefix before bootstrap. This workspace was tested with Rust 1.96, OpenSSL 3.6.3 and `/usr/local/opt/openssl@3.6`.

A source build uses the upstream package and Cargo.lock. Keep the linked OpenSSL libraries installed. Linux and ARM64 use upstream binary wheels where available. Do not downgrade cryptography to regain an older binary wheel: the previous compatibility version had published advisories.

Reference: https://cryptography.io/en/latest/installation/ .

## Local services

| Service                                 | Loopback port |
| :-------------------------------------- | :------------ |
| Studio                                  | 3000          |
| API / OpenAPI docs                      | 8080          |
| PostgreSQL / app and Temporal databases | 55432         |
| Redis                                   | 56379         |
| Temporal                                | 7233          |
| Keycloak                                | 8081          |
| MinIO / console, when available         | 9000 / 9001   |

`make infra-core` waits for the baseline services and starts no model-provider connection. `make migrate seed-core` applies Alembic and idempotently creates the local synthetic tenant. Run `make api`, `make worker` and `make dashboard` in separate terminals.

The full storage profile uses `make infra`, `make migrate seed-demo`, then `make dev` for application containers. The default MinIO registry image was unavailable in this environment, so the full profile is not verified. An explicit source-build override is available:

```sh
docker compose \
  -f infrastructure/compose/compose.yaml \
  -f infrastructure/compose/source-storage.yaml \
  up -d --build minio
```

This builds the tagged upstream MinIO source in a separate container build and retains its license/notice. It is a development workaround, not a production storage recommendation. Use the same override for subsequent MinIO Compose operations.

`/healthz` checks process liveness. `/readyz` checks the database migration, Redis, Temporal and S3 bucket. A dependency failure returns 503. Core fixture execution can work while storage readiness fails; never treat that as full-stack readiness.

## Verification

```sh
make lint typecheck test
make integration
make e2e
make e2e-ui
make build
```

`make integration` requires a migrated local PostgreSQL database. It creates synthetic records and verifies tenant RLS, connection-pool context, concurrent budget reservations and immutability. Use a disposable development database; never point tests at production.

For browser tests, API/worker/studio must be running. `scripts/browser.py` reads the private token from local settings and passes it to Playwright without printing it. Install Chromium once:

```sh
npm exec --workspace apps/dashboard -- playwright install chromium
make e2e-ui
```

Alternatively set `AG_CHROME_PATH` to an existing Chrome executable. On this Intel macOS host it is `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

Capture documentation images explicitly with `make screenshots`. Standard tests write screenshots, traces and HTML reports only under ignored test-output directories.

### Crash-after-commit recovery

Keep the API running and stop the ordinary dispatch worker. Run:

```sh
make recovery
```

The script starts a worker for a dedicated task queue, approves an exact simulated action, verifies an UNKNOWN action after commit, kills its worker and starts a replacement. It asserts one order, RECONCILED and SUCCEEDED. Restart `make worker` afterwards. The script terminates only its own child processes; the activity timeout makes the check take approximately 45 seconds on the reference host.

## Custom MCP setup

`make mcp-config` creates a private client entry under `.local/mcp.json` using the local human development identity, then issues an expiring service key with read/write/run scopes. It never forwards the human token to the MCP process. `make mcp-smoke` launches the actual stdio server and verifies tool discovery, service scopes and an authorized API round-trip. The API must be running; a worker is needed only when executing runs.

Regenerating the config rotates its previous key on the same API origin. The config is a secret, not a README example. Its executable path is local to this checkout; regenerate after moving the project. Keys expire after 24 hours. Other deployments should provision scoped keys through an authorized administrator.

## Schemas and packages

`make schema` exports OpenAPI from the current API and regenerates the TypeScript API types. Commit generated API contracts with their source changes. `make build` creates a Python wheel/source distribution, a standalone Next.js build and the TypeScript SDK output.

Container builds use non-root runtime stages. The dashboard copies only traced standalone runtime dependencies. These are packaging improvements; production runtime admission still fails until the roadmap's mandatory controls exist.

## GitHub and publication

Push the source, lockfiles, workflows, useful docs and screenshots. `.env`, the original local planning archive, editor settings, dependencies, databases, package outputs and test reports are ignored. The Packages workflow creates downloadable artifacts; it does not publish to registries or deploy.

Set branch protection to require the CI and Security checks after their first successful run. Enable private vulnerability reporting before inviting public security reports. Confirm owner attribution before a public release. No repository URL, contact address or passing hosted-CI badge is invented.

## Data and shutdown

`make down` stops Compose services and preserves named database/artifact volumes. Stop host API, worker and dashboard terminals separately. Do not delete volumes to resolve migration errors.

The initial Alembic downgrade is intentionally disabled because it destroys history. Restore drills, production backup/retention policies and upgrade runbooks are still required. The original build spec and session evidence are preserved locally in ignored `.local/archive`; the public roadmap records the remaining product scope.
