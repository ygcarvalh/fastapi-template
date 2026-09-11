# Contributing

## Setup

```bash
uv sync
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

Python 3.13 and [uv](https://docs.astral.sh/uv/). `.python-version` and `requires-python` pin the interpreter. The app refuses to start while `SECRET_KEY` is still the placeholder, which is why the generation step is not optional. `docker compose up --build` is the shorter path if you would rather not run PostgreSQL yourself; see the README for what it provisions.

## Before you push

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
uv run pytest --cov
uv run pip-audit
```

There is no CI workflow, so those five commands are the whole gate — and the hooks are what stop you from forgetting them. Install them once:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

ruff and mypy run on commit, `scripts/check-commit-messages.sh` checks the subject of every commit message, and the suite runs on push, against the real test database. `pip-audit` joins the push whenever `pyproject.toml` or `uv.lock` is part of it. The suite runs on push rather than on commit because it is too slow to pay for every commit and too important to leave to memory.

The suite needs a reachable `TEST_DATABASE_URL`, and the role owning it needs `CREATEDB`, because `tests/integration/test_migration_drift.py` provisions a throwaway database, applies every migration, and diffs the result against `Base.metadata`.

## Commits

Conventional Commits, header only, imperative mood, no trailing period. Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`. Put the reasoning in the pull request instead of the commit body. Keep 50 characters or fewer by hand. `scripts/check-commit-messages.sh` checks the type prefix rather than the length, so Dependabot's longer subjects still pass. The `commit-msg` hook runs it on the message you are writing; given a range it checks history instead.

```bash
scripts/check-commit-messages.sh          # defaults to origin/main..HEAD
scripts/check-commit-messages.sh .git/COMMIT_EDITMSG
```

Pull requests are squash merged, so the squashed subject is what lands on `main` and what the changelog is generated from. Make it describe the change as a whole rather than leaving GitHub's default.

## Layout

Dependencies point inward: `Router → Service → Repository → PostgreSQL`.

```
app/
  api/v1/routes/     # HTTP layer: validation, status codes, no business logic
  api/deps.py        # composition root; wires concrete repositories in
  services/          # business rules, HTTP-agnostic, raise domain exceptions
  services/protocols.py  # the repository interfaces the services depend on
  repositories/      # the only layer that queries the database
  models/            # SQLAlchemy entities
  schemas/           # Pydantic request and response contracts
  core/              # config, security, domain exceptions, feature flags
  core/http/         # error envelope, security headers, CORS, body limit, rate limiting
  core/observability/  # logging, correlation ids, access log, metrics
  db/                # declarative base, column mixins, engine and session
```

Three rules hold this together.

Services never import `app/repositories`. They depend on `Protocol` interfaces they own in `app/services/protocols.py`, and the concrete repositories are wired in at `app/api/deps.py`. Because mypy covers `tests` as well as `app`, a repository or a test fake that drifts from a protocol fails type checking rather than a test.

The transaction boundary is the request. `get_session` commits on success and rolls back on error, so services and repositories only `flush`. A service that commits on its own breaks the guarantee that a failed request leaves nothing behind.

`app/core` imports nothing from the layers outside it. Anything that needs a repository or a service to do its job is wiring, and wiring lives next to the composition root: `app/api/request_recorder.py` is the example, handed to the access-log middleware as a callable so the middleware never learns where rows go.

Routes call one use case each. `DELETE /users/me` calls `UserService.deactivate`, which soft-deletes the account's items and then the account; `POST /auth/password` calls `AuthService.change_password`, which re-verifies, rehashes and revokes every refresh token. A rule that two steps belong together is a service's rule, so a second caller cannot forget half of it.

Adding a resource means copying the `Item` slice across those layers and including the new router in `app/api/v1/router.py`. Routers are private by default; see the README on the public and private split before adding a `public_router` route.

## Tests

```bash
uv run pytest                       # whole suite
uv run pytest tests/unit -v         # fast, no database
uv run pytest path::test_name -v    # a single test
uv run pytest --cov                 # fails under 90%
```

`tests/unit` covers logic against the typed fakes in `tests/unit/fakes.py`. `tests/integration` drives routes through a real PostgreSQL test database, wrapping each test in a transaction it rolls back afterwards, so tests stay isolated without rebuilding the schema between them.

Write the test first. New behavior needs a test; a bug fix needs the regression test that fails before the fix.

The schema is created once per session with `Base.metadata.create_all`, and Alembic remains the source of truth for real databases. Changing a model without generating a migration fails the suite.

## Releases

`CHANGELOG.md` is generated from the commit history with [git-cliff](https://git-cliff.org), configured under `[tool.git-cliff]` in `pyproject.toml`. Nothing diffs it against a fresh generation. Pull requests are squash merged, so the squashed subject replaces the branch subjects the file was written from, and a check like that can never pass.

To cut a release, bump `version` in `pyproject.toml`, regenerate the changelog, then tag:

```bash
uv run git-cliff --output CHANGELOG.md
git tag -a v0.3.0 -m v0.3.0
git push origin v0.3.0
```

Nothing automates the release notes, so write them from the regenerated changelog when you open the GitHub release. Versioning is semver, and while the major stays at 0 a breaking change to the template's layout or configuration is a minor bump.

The changelog tracks the template itself. Clear it when you start a project from this repository, since the history belongs to the template rather than your service.
