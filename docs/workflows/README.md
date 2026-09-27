# GitHub Workflow Automation

This document describes the branching model, branch protection, and the GitHub Actions workflows that automate CI, versioning, releases, and PyPI publishing for `pyhive-integration`.

---

## Branching model

```
feature/* ──PR──▶ dev ──PR──▶ master ──tag/release──▶ PyPI
```

- **`feature/*`** — All work happens on feature branches.
- **`dev`** — Integration branch. Receives all feature PRs. Holds the next-version code.
- **`master`** — Release branch. Only ever receives merges from `dev`. Each merge produces a tagged GitHub Release and a PyPI publish.

Direct pushes to `dev` and `master` are blocked via branch protection rules.

---

## Branch protection rules (configured in GitHub Settings)

### `master`
- Require a pull request before merging.
- Required status checks:
  - `source-branch-is-dev` (from `guard-master.yml`)
  - All CI jobs from `ci.yml`
- Do not allow bypassing.
- Include administrators.

### `dev`
- Require a pull request before merging.
- Required status checks: all CI jobs from `ci.yml`.
- Allow any feature branch as PR source.

---

## End-to-end automated flow

1. Developer opens a PR from `feature/x` into `dev`. CI runs.
2. PR reviewed and merged into `dev`.
3. **`dev-release-pr.yml`** fires:
   - If no open `dev → master` PR exists, it bumps the patch version in `setup.py`, commits to `dev` with `[skip ci]`, and opens a `dev → master` PR.
   - If an open PR already exists, it does nothing (the PR auto-updates with the new commit).
4. Subsequent feature PRs into `dev` keep updating the same release PR — **no further version bumps**.
5. When ready to release, the maintainer merges the `dev → master` PR.
6. **`guard-master.yml`** ensured the PR's source was `dev`; the merge is allowed.
7. **`release-on-master.yml`** fires on the push to `master`:
   - Reads the version from `setup.py`.
   - Creates tag `vX.Y.Z` and a GitHub Release with auto-generated notes.
8. **`python-publish.yml`** fires on `release: published`:
   - Builds the sdist + wheel.
   - Uploads the wheel as a release asset.
   - Publishes to PyPI via Trusted Publishing.

---

## Workflow reference

### `ci.yml` — Continuous Integration
- **Triggers:** all `pull_request` events; `push` to `master`.
- **Purpose:** Lint (bandit, black, codespell, flake8, isort, json, pyupgrade, etc.) and tests.
- **Role:** Gates every PR via required status checks. Provides a final sanity run on `master` after a release PR merges.

### `guard-master.yml` — Master branch guard
- **Triggers:** `pull_request` targeting `master`.
- **Purpose:** Fails the check if the PR's source branch is anything other than `dev`.
- **Role:** Enforces the "only dev → master" rule. Must be a required status check on `master`.

### `dev-release-pr.yml` — Release PR + version bump
- **Triggers:** `push` to `dev`.
- **Purpose:**
  - Checks for an open `dev → master` PR.
  - If none exists: bumps the patch version in `setup.py`, commits with `[skip ci]`, opens the release PR.
  - If one exists: no-op.
- **Role:** Guarantees exactly one version bump per release cycle, regardless of how many feature PRs land on `dev`.

### `release-on-master.yml` — Tag + GitHub Release
- **Triggers:** `push` to `master`.
- **Purpose:**
  - Reads the version from `setup.py`.
  - Skips if a tag for that version already exists.
  - Otherwise creates tag `vX.Y.Z` and a GitHub Release with auto-generated notes.
- **Role:** The bridge between merging the release PR and triggering PyPI publishing.

### `python-publish.yml` — PyPI publish (release-driven)
- **Triggers:** `release: published`.
- **Purpose:**
  - Builds the sdist and wheel with `python -m build`.
  - Uploads the wheel as a GitHub Release asset.
  - Publishes to PyPI via OIDC Trusted Publishing (`pypi` environment).
- **Role:** Primary production publish path.

### `dev-publish.yml` — Manual dev/ad-hoc PyPI publish
- **Triggers:** `workflow_dispatch` (manual only).
- **Purpose:** Build and publish to PyPI from a non-master branch on demand.
- **Role:** Used for ad-hoc dev releases when something needs to be pushed to PyPI without going through the full `dev → master` release cycle. Refuses to run on `master`.

---

## Required GitHub configuration

### Environments
- **`pypi`** — Used by `python-publish.yml` and `dev-publish.yml`. Configure as a Trusted Publisher on PyPI for this repository.

### Required status checks on `master`
- `source-branch-is-dev`
- All CI job names from `ci.yml`.

### Required status checks on `dev`
- All CI job names from `ci.yml`.

### Permissions
The workflows use `GITHUB_TOKEN` with `contents: write` and `pull-requests: write` where needed. No additional PATs required.

---

## Removed (redundant) workflows

The following workflows were removed during this consolidation:

- **`python-package.yml`** — Stand-alone flake8 lint duplicated by the `lint-flake8` job in `ci.yml`.
- **`release_draft.yml`** — Manual `release-drafter` workflow superseded by automatic GitHub-native release notes in `release-on-master.yml`.

---

## Versioning

- Source of truth: `version="X.Y.Z"` in `@/setup.py`.
- Bumped automatically (patch only) by `dev-release-pr.yml` once per release cycle.
- For minor or major bumps, edit `setup.py` manually on `dev` before the first feature PR merges, or amend the bump commit before merging the release PR.

---

## Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| Release PR didn't open | Push to `dev` was the bot's own bump commit (contains `[skip ci]` and `chore: bump version` — intentionally skipped). |
| Version not bumped | A `dev → master` PR was already open. Bumps happen only when opening a fresh release PR. |
| PyPI publish skipped | Tag for current `setup.py` version already exists; bump the version before merging to `master` again. |
| PR into `master` fails check | Source branch is not `dev`. This is enforced by `guard-master.yml`. |
| Manual dev publish fails on master | Intentional — `dev-publish.yml` refuses to run on `master`. Switch branch or use the standard release flow. |
