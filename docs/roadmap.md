# Roadmap and production readiness

The working release is a development foundation with a deterministic procurement workflow. This document distinguishes shipped behavior from the larger target product.

| Area                   | Current state                                                                                              | Remaining delivery                                                                                                                   |
| :--------------------- | :--------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------- |
| Foundation             | Locked workspaces, local infrastructure, migrations, auth primitives, CI definitions                       | Verified full storage bootstrap, restricted service/catalog roles, operational telemetry and hosted CI evidence                      |
| Genomes                | Strict validation, canonical hashing, immutable publication and manifest export                            | Draft concurrency/ETags, import, branch/diff/merge, complete lineage and portable signed bundles                                     |
| Runtime                | Temporal procurement fixture, checkpoints, exact-action approval, cancellation, budgets and ordered events | Live provider registry/accounting, complete strategies, schema repair, policy/version pinning, rate limits and orphan reconciliation |
| Context and knowledge  | Unsupported features reject admission                                                                      | Context disclosure/compaction, skill registry, verified scoped memory and reviewed procedures                                        |
| Secure execution       | Trusted fixture tools and a scoped local MCP server                                                        | Separate authenticated broker, hardened sandbox, PTC, external MCP clients and A2A                                                   |
| Reliability lab        | Targeted fault/recovery tests                                                                              | Three stateful simulation environments, assertion DSL, trace replay, chaos suites and measured benchmarks                            |
| Evolution              | Not implemented                                                                                            | Protected candidate optimization, independent held-out evaluation, signed approval, inheritance and canary/rollback                  |
| Studio and clients     | Initial workspace, publication/run/approval/evidence flow, async Python transport, CLI basics and TS types | Full OIDC browser flow, all screens, browser SSE reconnect, pagination, accessibility audit, full SDKs and framework integrations    |
| Operations and release | Initial non-root container builds and local security tests                                                 | Helm, backup/restore drills, workload/SLO tests, image scans, signed artifacts and release ownership details                         |

## Production readiness

**Production deployment is blocked.** The backend deliberately rejects `AG_PROFILE=production`, including configurations that merely set a sandbox verification flag. Repository cleanup or container optimization cannot safely replace these controls.

Required before production:

- Execute live providers with enforced pricing, usage, deadlines and approved routing.
- Verify hardened sandbox infrastructure and independent broker authorization.
- Finish policy versioning/revalidation, service identities and least-privilege database roles.
- Complete tenant isolation across all future memory, artifact, trace and sandbox paths.
- Verify S3 persistence, retention, secrets management and backup/restore.
- Complete OIDC browser authentication, authorization/revocation flows and security review.
- Run complete integration, accessibility, load, dependency/image and deployment checks on the supported target.
- Configure TLS, network policies, operational monitoring and incident/upgrade procedures.
- Supply the owner copyright details and a verified private security-reporting mechanism.

No chart, provider, sandbox, benchmark or compliance capability is advertised as working without its real path and verification evidence.

## Verification record

Local reference environment: macOS 26.5.1 x86_64, Python 3.11, Node 24 and Docker Desktop. The existing development increment passed unit/security, real PostgreSQL, actual Temporal recovery and browser checks. CI definitions still require execution in the target GitHub repository; GitHub Actions success is not inferred from local results.

Verified locally on 2026-11-26:

| Check                              | Result                                                                                                                        |
| :--------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| Unit and security suite            | 52 passed, including scoped MCP authorization, tenant isolation, input limits and deadlines                                   |
| Real PostgreSQL integration        | 3 passed                                                                                                                      |
| Standalone dashboard browser suite | 3 passed, including actual procurement and security headers                                                                   |
| MCP stdio smoke test               | 10 tools discovered; authenticated identity and agent-list API round-trip passed                                              |
| MCP key regeneration               | Previous key revoked; new private configuration round-trip passed                                                             |
| Formatting and typing              | Ruff, Prettier, strict mypy and dashboard/SDK TypeScript checks passed                                                        |
| Packages                           | Python wheel/source distribution, standalone dashboard and TypeScript SDK built                                               |
| Workflows                          | All GitHub workflows passed actionlint; hosted runs still pending                                                             |
| Container definitions              | Docker build checks passed for API and dashboard with no warnings; full image runtime/scan verification pending               |
| Dependencies                       | Python advisory audit reported no known vulnerabilities; npm install audit reported zero vulnerabilities                      |
| Documentation                      | Real workspace and completed-run screenshots captured; original planning evidence preserved only in the ignored local archive |

Full clean-checkout startup with storage, Linux hardened isolation, live model calls, deployment clusters and production performance remain unverified.
