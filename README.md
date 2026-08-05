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

Login does not reveal whether an account exists. A wrong password and an unknown address
both pay for a full bcrypt verification and come back with the same 401. Drop the dummy
hash on the unknown-address path and the two diverge by roughly 300 ms, which is enough
to enumerate the whole user table over the network.

Registration does reveal it, by answering 409 when an address is already taken. That is a
deliberate trade for a usable signup form, and it is the one place the template leaks
account existence. Closing it properly means answering 202 either way and sending a
verification email, which needs a mail provider and a tokens table.

Error responses never echo what was submitted. The validation handler keeps `type`, `loc`
and `msg` and drops `input`, because FastAPI's default 422 body repeats the rejected
value, which would put passwords in response bodies and access logs. Unexpected
exceptions return a flat 500 and log the traceback server side, so stack traces and
connection strings stay internal.

Passwords run from 8 to 72 bytes. bcrypt refuses anything longer, so without the ceiling
a long passphrase turns into an unhandled 500 on an unauthenticated route.

`SECRET_KEY` must be at least 32 characters and cannot be the example value; the app
refuses to start otherwise. `JWT_ALGORITHM` accepts only HS256, HS384 and HS512, so a
stray environment variable cannot downgrade token verification.

CSRF protection is absent deliberately. Authentication is bearer-token only and nothing
sets a cookie, so a cross-site request has nothing to ride on. Add it if you introduce
cookie sessions. CORS is unconfigured for the same reason it is safe to leave alone: with
no origins allowed, browsers block cross-origin calls by default. If you add
`CORSMiddleware`, name the origins instead of using `*`.

Rate limits on the auth endpoints come from `LOGIN_RATE_LIMIT` and
`REGISTER_RATE_LIMIT`. The default limiter counts in memory, so counts reset on restart
and are per worker. Point slowapi at Redis before running more than one.

Three settings to change before you deploy:

- `HSTS_ENABLED=true`, once TLS terminates in front of the app. It ships off so local
  HTTP works.
- `DOCS_ENABLED=false`, to withdraw `/docs`, `/redoc` and `/openapi.json`.
- `?ssl=require` appended to `DATABASE_URL`, which asyncpg reads when it connects.

## Roles and timestamps

Every table inherits `TimestampMixin` from `app/db/mixins.py`, which supplies
`created_at` and an `updated_at` that PostgreSQL refreshes on write. Both come from
`now()`, which returns the transaction start time, so a row created and modified inside
one transaction carries identical values. They diverge once the writes land in separate
transactions, which is what a request per change gives you.

`User.role` is a `String(20)` mapped to the `UserRole` string enum rather than a
PostgreSQL enum type. Adding a role is then an ordinary code change instead of an
`ALTER TYPE` in a migration. Guard a route with the `require_role` factory:

```python
@private_router.get("", dependencies=[require_role(UserRole.ADMIN)])
async def list_users(...): ...
```

A caller without the role gets 403 and `{"detail": "Insufficient permissions"}`, while a
caller without a token still gets 401, because the router-level `RequireAuth` runs first.
New accounts are created as `user`; promote deliberately.

## Tokens

`POST /api/v1/auth/login` returns a short-lived access token and a longer-lived refresh
token. `POST /api/v1/auth/refresh` exchanges the refresh token for a fresh pair, so the
old one stops being the only key to the account.

Both tokens carry a `typ` claim, and each decoder insists on its own value. Without that
check a refresh token would work as a bearer token on any protected route, which hands
back the long lifetime the short access expiry was meant to avoid. The template tests
both directions of that confusion.

Refresh tokens are stateless, which buys a refresh with no database write but means you
cannot revoke one before it expires. `REFRESH_TOKEN_EXPIRE_DAYS` is therefore the window
in which a stolen token stays useful, so keep it in days. Deactivating an account does
end refreshing immediately, because `refresh` reloads the user and the repository filters
soft-deleted rows. If you need real revocation, store the refresh tokens hashed with a
`revoked_at` column and check them on refresh.

## Soft delete

`DELETE /api/v1/items/{id}` and `DELETE /api/v1/users/me` stamp `deleted_at` instead of
removing rows, so the history survives an accidental delete. Repositories filter on
`deleted_at IS NULL`, which is written out in each query rather than installed as a
global loader rule, because a query that quietly rewrites itself is hard to reason about
in a template you are about to copy.

Two details are easy to get wrong:

- A plain unique constraint on `email` would keep a deactivated address reserved
  forever, so the address becomes unusable rather than free. The template uses a partial
  unique index instead, `unique on (email) where deleted_at is null`, which still
  rejects two active accounts on one address while letting a deactivated one register
  again.
- `User.items` cascades with `all, delete-orphan`, which deletes rows outright. So
  deactivating an account retires its items through `ItemService.delete_all_for_owner`
  before the user row is stamped, and the ORM cascade stays reserved for a real hard
  delete.

Deactivation ends access immediately: `get_by_email` and `get` both filter deleted rows,
so a deactivated account cannot log in and an already issued token stops working on the
next request.

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
