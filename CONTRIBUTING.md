## Contributing

This repository follows a lightweight but explicit governance model.

### Ground Rules

- Keep changes scoped. Do not mix feature work, packaging changes, and unrelated refactors in one PR.
- Prefer existing project patterns over new abstractions.
- Release artifacts are published from tagged versions, not from random development commits.

### Branch / PR Expectations

- Use descriptive branches such as `feat/theme-toggle` or `fix/windows-picker-dpi`.
- Use Conventional Commits in commit messages:
  - `feat:`
  - `fix:`
  - `docs:`
  - `build:`
  - `ci:`
  - `refactor:`
  - `test:`

### Labels

Issues and PRs are expected to use labels for:

- type: feature / bug / docs / ui / packaging / chore
- area: core / ui / windows / macos / release
- priority: p0 / p1 / p2
- release: major / minor / patch

### Release Policy

- Versioning uses SemVer: `vMAJOR.MINOR.PATCH`
- Stable releases should represent installable end-user builds
- Pre-releases are reserved for preview or validation builds
- User-facing changes should be reflected in `CHANGELOG.md`

### Local Validation

Run before opening a PR:

```bash
.venv/bin/python -m pytest -q
git diff --check
```

