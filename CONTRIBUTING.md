# Contributing

Short, practical rules for working on Bekaa3D with more than one person. For architecture, naming, and invariants see [`CLAUDE.md`](CLAUDE.md); the specification itself is [`docs/SRS.md`](docs/SRS.md).

## Branching and review

- **No direct commits to `main`.** Every change arrives through a pull request, including one-line documentation fixes.
- **One branch per vertical slice.** Name it after the slice: `vs-004-password-reset`. Non-slice work uses a prefix: `chore/`, `docs/`, `fix/`.
- **Pull `main` before starting a slice**, and again before opening the PR:

  ```bash
  git checkout main
  git pull
  git checkout -b vs-004-password-reset
  ```

- **A PR needs review and green CI before it merges.** CI runs `ruff check`, `ruff format --check`, `mypy src`, and the full `pytest` suite. Don't merge on `mergeable_state: unstable` — that means checks are still running.
- Keep a slice's PR self-contained: it should not depend on unfinished work in another branch (Definition of Done in [`docs/vertical-slice-plan.md`](docs/vertical-slice-plan.md)).

## The Alembic migration lock

**Only one person may be creating a migration at any time.**

Alembic's history is a linked list: each revision names the one before it in `down_revision`. When two branches are cut from the same head and both run `alembic revision`, both new revisions point back at that same parent, and the chain forks:

```
              ┌─ VS-004 migration
A (head) ─────┤
              └─ VS-005 migration      ← two heads. Broken.
```

What the chain must look like:

```
A ──→ VS-004 migration ──→ VS-005 migration      ← one head. Correct.
```

The fork surfaces as `Multiple head revisions are present` on the next `alembic upgrade head`, and it blocks *everyone* until it is resolved.

### The protocol

1. **Announce it** before running `alembic revision` — "I'm taking the migration lock." Message, call, whatever you use; the point is that the other person knows.
2. **The other developer waits.** Not "starts a migration carefully" — waits. Keep working on domain, application, API, and test code, which need no lock.
3. **Merge your migration PR**, then say the lock is free.
4. **The other developer pulls `main`** and only then runs `alembic revision`. Their new revision now points at yours, and the chain stays linear.

Hold the lock for as short a time as you can. If a slice needs a migration, generate it early and get that PR merged rather than sitting on the lock while the rest of the slice is built.

### Before merging any migration PR

Run both, and don't merge unless both pass:

```bash
docker compose exec api alembic heads          # must list exactly ONE revision
docker compose exec api alembic upgrade head   # must succeed
```

Also confirm the migration is reversible — `alembic downgrade -1` then `alembic upgrade head` — before you open the PR. A migration that cannot be undone is a migration you cannot roll back in production.

### If you do end up with two heads

**Do not casually edit `down_revision` to stitch them together.** It looks like it works, and it silently reorders DDL that may depend on ordering — a column added by one branch, indexed by the other. Instead:

- If neither migration has been merged, the cheapest fix is to delete the later revision file, pull `main`, and regenerate it against the correct parent.
- If both are already on `main`, use `alembic merge` to create an explicit merge revision, and have the second person review it. Editing `down_revision` by hand is a last resort and never done alone.

## Local checks before opening a PR

```bash
ruff check . && ruff format --check . && mypy src tests && pytest
```

Integration and concurrency tests need Docker running — they start real PostgreSQL and Redis containers.

### Timing tests (run manually)

Tests marked `timing` check that enumeration-sensitive endpoints (register, resend-verification, password-reset request, login) answer in the same time whether or not the account exists, and that password hashing never blocks the event loop. They compare wall-clock latency, so they depend on the machine and are **excluded by default and in CI** (`addopts` carries `-m 'not timing'`). Machine-independent versions of the same guarantees (equal Argon2 work per branch, hashing off the event loop) run in the normal suite.

Run them on a quiet machine, without coverage (they skip themselves under a tracer), and more than once:

```bash
pytest -m timing
for i in 1 2 3; do pytest -m timing -q; done   # three runs, as for any timing claim
```

A later `-m` on the command line overrides the default one from `addopts`. A failure means the two branches' interquartile latency ranges no longer overlap — an attacker can tell them apart from response time alone.

## Dependencies

Two layers, with different jobs:

- **`pyproject.toml`** declares ranges: the floor is the version the suite was last run against, the ceiling the next major where the package follows semver.
- **`requirements.txt`** (runtime) and **`requirements-dev.txt`** (runtime + `dev` extra) are the lock: every package, direct and transitive, pinned exactly and hash-checked, resolved for Python 3.13 on every platform. CI and the Docker image install only from these, so every environment runs the versions the suite was run with.

Install for development:

```bash
pip install --require-hashes -r requirements-dev.txt
pip install --no-deps -e .
```

To add or upgrade a dependency, change `pyproject.toml`, then regenerate **both** locks with [uv](https://docs.astral.sh/uv/) and commit them together with the change and a green suite:

```bash
uv pip compile pyproject.toml --universal --python-version 3.13 --generate-hashes -o requirements.txt
uv pip compile pyproject.toml --extra dev --universal --python-version 3.13 --generate-hashes -o requirements-dev.txt
```

`uv pip compile` keeps every existing pin it can; add `--upgrade-package <name>` to move one package, or `--upgrade` to move everything. Never edit the lock files by hand.

## Secrets

`.env` is git-ignored and must never be committed. Copying `.env.example` is not enough: replace every placeholder with a locally generated value. See the **Local secrets** section in [`CLAUDE.md`](CLAUDE.md) for why `IP_HASH_SALT` in particular matters.
