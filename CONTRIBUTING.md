# Contributing

Start with [README](README.md), [Architecture](docs/architecture.md) and [Roadmap](docs/roadmap.md). Follow [Development](docs/development.md) for environment and integration setup.

Before opening a pull request:

```sh
make format
make lint typecheck test
make integration
make build
```

Run the relevant API/Temporal/browser checks for behavioral changes. Add meaningful authorization and failure-path tests. Record skipped or unavailable checks separately from passes. Regenerate API types with `make schema` when contracts change.

Keep changes focused. Do not introduce placeholder endpoints, invented metrics or silent production fallbacks. Preserve the production startup gate until the required controls are actually implemented. Never commit `.env`, credentials, customer data, generated packages or test reports.

GitHub workflows build and check artifacts without publishing or deploying automatically. Security reports follow [SECURITY.md](SECURITY.md).
