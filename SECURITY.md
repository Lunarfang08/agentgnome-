# Security

AgentGenome is development software. Production startup is intentionally blocked. Do not expose the development stack publicly or supply real financial/customer credentials to its fixture tools.

## Reporting

The repository owner must enable a verified private vulnerability-reporting mechanism before a public release. No security email address has been supplied. If private reporting is not available, do not post sensitive exploit details or credentials in public issues.

## Implemented controls

- Unique local development tokens, private `.env` files and no committed runtime secrets.
- JWT signature, issuer, audience and expiry checks; membership/scoped authorization.
- Hashed expiring/revocable API keys and repeated authorization at API boundaries.
- Initial tenant filters and transaction-local PostgreSQL FORCE RLS.
- Immutable published genomes and terminal runs; append-only event/audit triggers.
- Bounded request bodies, structured errors, parameterized queries and security headers.
- Exact-action approvals, idempotent admission, atomic budget reservations and simulated side-effect reconciliation.
- HTTP-only SameSite browser cookies, server-side API requests and Next.js server-action origin checks.
- Production denial for development identity, fixture provider and missing hardened isolation.

## Custom MCP server

The local stdio server delegates all operations to the API and requires a scoped `ag_` service key. Setup grants read/write/run with a 24-hour expiry and no approval/admin scope. There are no approval, arbitrary HTTP, shell or API-key management tools. IDs, manifests, input sizes and pagination are validated; API calls have a total deadline and response-size cap. Redirects are not followed. HTTP is limited to loopback; remote API origins require HTTPS. The private client config is ignored by Git and written with owner-only permissions on supported systems.

The API rechecks each request, so key revocation, tenant boundaries and budget/approval requirements remain effective. MCP tool annotations are advisory and do not grant permissions. Public Streamable HTTP hosting and external MCP connectors are not implemented.

## Threat model and open boundaries

| Boundary              | Protected assets                                | Remaining controls                                                               |
| :-------------------- | :---------------------------------------------- | :------------------------------------------------------------------------------- |
| Browser → API         | Tokens, memberships, authorized actions         | Complete OIDC browser flow, full script CSP and browser security assessment      |
| API → database        | Tenant records, genomes, budgets                | Separate restricted service/catalog roles and complete future-resource coverage  |
| Workflow → tool       | Approval intent and external side effects       | Independent authenticated broker and versioned policy checks for real connectors |
| Generated code → host | Host credentials, network and tenant workspaces | Hardened isolation not implemented; generated code is not admitted               |
| Evidence → storage    | Audit, context and artifacts                    | Signed/hash-chained evidence, complete redaction, retention and restore controls |

Database triggers do not defend against an administrator altering the schema. A worker with the development DB role is not a fully isolated production service identity. Current fixture recovery tests do not establish universal exactly-once execution for external systems.

## Supply chain

Python/npm dependencies are locked; GitHub Actions are pinned to commit hashes. Security workflows run advisory audits and CodeQL. Image/OS scans, complete deployment review and signed release artifacts are still required. A dependency audit is not a compliance certification.

See [production readiness](docs/roadmap.md#production-readiness) for the release gate. The local development token is never a production credential; bootstrap rotates the former shared token while preserving custom secrets.
