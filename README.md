# FastAPI Backend Template

A clone-and-launch starter for FastAPI backends: async SQLAlchemy 2.0 + PostgreSQL,
Alembic migrations, JWT authentication, a layered (Router → Service → Repository)
architecture, and a test-first setup.

## Architecture

```
Request → Router (HTTP) → Service (business logic) → Repository (DB) → PostgreSQL
```

- `app/api/v1/routes` — HTTP layer (validation, status codes), no business logic.
- `app/services` — business rules, HTTP-agnostic, raises domain exceptions.
- `app/services/protocols.py` — the repository interfaces the services depend on.
- `app/repositories` — the only layer that queries the database.
- `app/models` — SQLAlchemy ORM entities.
- `app/schemas` — Pydantic request/response contracts.
- `app/core` — config, security (JWT + password hashing), domain exceptions.
- `app/db` — declarative base and async session factory.

The transaction boundary is the request: `get_session` commits on success and rolls
back on error, so services and repositories only `flush`. Domain exceptions
(`NotFoundError`, `ConflictError`, `AuthError`) are mapped to HTTP responses by
handlers registered in `app/main.py`.

Dependencies point inward. Services never import `app/repositories`; they depend on
`Protocol` interfaces they own in `app/services/protocols.py`, and the concrete
repositories are wired in at the composition root (`app/api/deps.py`). Because mypy
covers `tests` as well as `app`, a repository or a test fake that drifts from a
protocol fails type checking.

An example `Item` resource (owned by a `User`, JWT-protected) demonstrates the full
slice end to end.

Collection endpoints are paginated. `GET /api/v1/items` accepts `limit` (1 to 100,
default 20) and `offset`, and returns a `Page` envelope — `items`, `total`, `limit`,
`offset` — from `app/schemas/pagination.py`. Reuse `PageParams` and `Page[T]` for new
collections rather than returning a bare list, so no endpoint is an unbounded query.

## Public and private routes

Routes are private by default. Each routes module names its routers after their
policy, and `app/api/v1/router.py` includes them in one place, so you can read the
whole public surface there:

- `public_router` — reachable without a token.
- `private_router` — declared with `dependencies=[RequireAuth]`, so every route inside
  it needs a valid bearer token whether or not the handler asks for `CurrentUser`.

Add `current_user: CurrentUser` to a handler that needs the caller's identity. Leaving
it out does not make the route public. `tests/integration/test_route_policy.py` reads
the OpenAPI schema and fails when a route is neither protected nor named in
`PUBLIC_OPERATIONS`, so forgetting to protect one breaks the build instead of leaking
data.

## Security posture

What the template does, and the decisions behind it.

- **Login does not reveal whether an account exists.** A wrong password and an unknown
  address both cost a full bcrypt verification and return the same 401 body. Without the
  dummy hash on the unknown-address path the two differ by roughly 300 ms, which is
  enough to enumerate every user in the database over the network.
- **Registration does reveal it**, by answering 409 when an address is already in use.
  That is a deliberate trade for a usable signup form, and it is the one place the
  template leaks account existence. Closing it properly means always answering 202 and
  sending a verification email, which needs a mail provider and a tokens table.
- **Errors do not echo input.** The validation handler keeps `type`, `loc`, and `msg` and
  drops `input`, because FastAPI's default 422 body repeats the rejected value, which
  puts submitted passwords into response bodies and access logs.
- **Unexpected exceptions return a flat 500** and log the traceback server side, so
  stack traces and connection strings stay out of responses.
- **Passwords are 8 to 72 bytes.** bcrypt refuses anything longer, so without the ceiling
  a long passphrase becomes an unhandled 500 on an unauthenticated route.
- **Auth endpoints are rate limited** through `LOGIN_RATE_LIMIT` and
  `REGISTER_RATE_LIMIT`. The default limiter counts in memory, so it resets on restart
  and counts per worker. Point slowapi at Redis before running more than one.
- **`SECRET_KEY` must be at least 32 characters and cannot be the example value.** The
  app refuses to start otherwise.
- **`JWT_ALGORITHM` accepts only HS256, HS384, and HS512**, so a stray environment
  variable cannot downgrade token verification.
- **CSRF protection is absent on purpose.** Authentication is bearer-token only and no
  cookies are set, so a cross-site request has nothing to ride on. Add CSRF protection if
  you introduce cookie sessions.
- **CORS is unconfigured**, which blocks cross-origin browser calls by default. If you
  add `CORSMiddleware`, name the origins instead of using `*`.
- **Set `HSTS_ENABLED=true` behind TLS.** It stays off by default so local HTTP works.
- **Set `DOCS_ENABLED=false`** to withdraw `/docs`, `/redoc`, and `/openapi.json`.
- **Reach the database over TLS** outside local development by appending `?ssl=require`
  to `DATABASE_URL`, which asyncpg reads when it connects.

## Quickstart with Docker

Requires Docker with Compose. Generate a secret first, because the app refuses to
start without one:

```bash
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
docker compose up --build
```

Compose starts PostgreSQL, waits for it to pass its healthcheck, applies migrations,
and serves the API on http://127.0.0.1:8000. The test database is created alongside
the main one by `scripts/create-test-database.sh`. Override `POSTGRES_PORT` or
`API_PORT` if those ports are already taken on your machine.

## Local setup without Docker

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A reachable PostgreSQL instance

Install dependencies and create your environment file:

```bash
uv sync
cp .env.example .env          # then edit credentials
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
```

Create the database role and databases (adjust names/password to taste, then keep
`.env` in sync):

```bash
sudo -u postgres psql \
  -c "CREATE ROLE fastapi_user LOGIN PASSWORD 'secret123' CREATEDB;" \
  -c "CREATE DATABASE fastapi_db OWNER fastapi_user;" \
  -c "CREATE DATABASE fastapi_db_test OWNER fastapi_user;"
```

The role needs `CREATEDB` because the migration check in
`tests/integration/test_migration_drift.py` provisions a throwaway database, applies
every migration to it, and compares the result against the models.

Apply migrations:

```bash
uv run alembic upgrade head
```

## Run the dev server

```bash
uv run fastapi dev app/main.py
```

Open http://127.0.0.1:8000/docs for the interactive API.

## Test-driven development

The suite uses a real PostgreSQL test database (`TEST_DATABASE_URL`) with a per-test
transaction that is rolled back — fast and fully isolated. The schema is created
once per test session with `Base.metadata.create_all`; Alembic remains the source of
truth for the real database.

Red → green → refactor:

1. Write a failing test under `tests/unit` (logic, mocked repository) or
   `tests/integration` (routes through the test DB).
2. Run it and watch it fail.
3. Write the minimal code to pass.
4. Refactor with the test as a safety net.

```bash
uv run pytest                       # whole suite
uv run pytest tests/unit -v         # fast unit tests
uv run pytest path::test_name -v    # a single test
```

## Adding a new resource

Copy the `Item` slice, renaming across the layers:

1. `app/models/<name>.py` — ORM model (register it in `app/models/__init__.py`).
2. `app/schemas/<name>.py` — Pydantic schemas.
3. `app/services/protocols.py` — the repository interface the service needs.
4. `app/repositories/<name>_repo.py` — queries implementing that interface.
5. `app/services/<name>_service.py` — business rules, depending on the protocol.
6. `app/api/v1/routes/<name>.py` — routes; include it in `app/api/v1/router.py`.
7. Add a dependency provider in `app/api/deps.py`.
8. Write unit + integration tests first, with fakes in `tests/unit/fakes.py`.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

Changing a model without generating a migration fails the suite. The check applies
every migration to a fresh database and diffs the result against `Base.metadata`, so
the two cannot drift apart silently.

## Changelog

`CHANGELOG.md` is generated from Conventional Commits, and CI fails when it is stale:

```bash
uv run git-cliff --output CHANGELOG.md
```

The file tracks changes to the template itself. Clear it when you start a project from
this repository, since the history belongs to the template rather than your service.

## Quality tooling

```bash
uv run pre-commit install     # enable hooks (once)
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy app tests         # type-check
uv run pytest --cov           # tests with coverage (fails under 90%)
uv run pip-audit              # known vulnerabilities in dependencies
```

CI runs all of these on every push and pull request, against a real PostgreSQL
service container.

## Project layout

```
app/
  main.py                 # app factory; lifespan, routers, exception handlers
  core/                   # config, security, exceptions
  db/                     # declarative base, engine and session lifecycle
  api/
    deps.py               # shared dependencies (session, current user, services)
    v1/
      router.py           # aggregates v1 routers, public ones first
      routes/             # auth, users, items
  models/                 # SQLAlchemy models
  schemas/                # Pydantic schemas, including pagination
  repositories/           # database access
  services/               # business logic
    protocols.py          # repository interfaces the services depend on
alembic/                  # migration environment + versions
scripts/                  # database bootstrap used by compose
tests/
  unit/                   # logic against typed fakes
  integration/            # routes through the test database
Dockerfile                # multi-stage build, non-root runtime
compose.yaml              # PostgreSQL + API, migrations on start
.github/workflows/ci.yml  # lint, types, tests, audit, changelog
```
