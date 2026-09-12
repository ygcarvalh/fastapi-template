# FastAPI Backend Template

[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A clone-and-launch starter for FastAPI backends: async SQLAlchemy 2.0 + PostgreSQL, Alembic migrations, JWT authentication, a layered (Router → Service → Repository) architecture, correlation IDs that reach the error body, and a test-first setup.

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
- `app/core` — config, security (JWT + password hashing), domain exceptions, feature flags.
- `app/core/http` — the middleware stack: error envelope, security headers, CORS, body limit, rate limiting.
- `app/core/observability` — structured logging, correlation IDs, the access log, Prometheus metrics.
- `app/db` — declarative base, shared column mixins, engine and session lifecycle.

The transaction boundary is the request: `get_session` commits on success and rolls back on error, so services and repositories only `flush`. Domain exceptions (`NotFoundError`, `ConflictError`, `AuthError`) are mapped to HTTP responses by handlers registered in `app/main.py`.

Dependencies point inward. Services never import `app/repositories`; they depend on `Protocol` interfaces they own in `app/services/protocols.py`, and the concrete repositories are wired in at the composition root (`app/api/deps.py`). Because mypy covers `tests` as well as `app`, a repository or a test fake that drifts from a protocol fails type checking.

An example `Item` resource (owned by a `User`, JWT-protected) demonstrates the full slice end to end.

Collection endpoints are paginated. `GET /api/v1/items` accepts `limit` (1 to 100, default 20) and `offset`, and returns a `Page` envelope — `items`, `total`, `limit`, `offset` — from `app/schemas/pagination.py`. Reuse `PageParams` and `Page[T]` for new collections rather than returning a bare list, so no endpoint is an unbounded query.

## Public and private routes

Routes are private by default. Each routes module names its routers after their policy, and `app/api/v1/router.py` includes them in one place, so you can read the whole public surface there:

- `public_router` — reachable without a token.
- `private_router` — declared with `dependencies=[RequireAuth]`, so every route inside it needs a valid bearer token whether or not the handler asks for `CurrentUser`.

Add `current_user: CurrentUser` to a handler that needs the caller's identity. Leaving it out does not make the route public. `tests/integration/test_route_policy.py` reads the OpenAPI schema and fails when a route is neither protected nor named in `PUBLIC_OPERATIONS`, so forgetting to protect one breaks the build instead of leaking data.

## Security posture

Login does not reveal whether an account exists. A wrong password and an unknown address both pay for a full bcrypt verification and come back with the same 401. Drop the dummy hash on the unknown-address path and the two diverge by roughly 300 ms, which is enough to enumerate the whole user table over the network.

Registration answers 409 when an address is already taken, from the check *and* from the write. The check cannot close the race on its own, so a unique violation raised by the flush is read and turned into the same 409 — any other constraint failure stays a 500, because that one is a bug rather than a conflict.

Registration does reveal existence, then, by answering 409 when an address is already taken. That is a deliberate trade for a usable signup form, and it is the one place the template leaks account existence. Closing it properly means answering 202 either way and sending a verification email, which needs a mail provider and a tokens table.

Every failing response has the same shape, whatever raised it:

```json
{"detail": "Email already registered", "message": "Email already registered", "request_id": "ab8f2c1d4e"}
```

`detail` is what the previous version returned, kept so a client that reads it keeps working. `message` is one sentence a frontend can put in front of a person. `request_id` is the correlation ID, which is also on the `X-Request-ID` header of the same response — including on a 500, where Starlette answers above the middleware that would otherwise set it, so the handler sets it itself.

Domain errors reuse their own detail as the message; 422, 429 and 500 carry a fixed sentence. Framework errors go through the same handler, so the 401 from the bearer scheme and the 404 for an unrouted path arrive in that shape too. `app/schemas/error.py` holds the models, and they are attached to the v1 router, so `/docs` shows the envelope instead of FastAPI's `HTTPValidationError`.

Error responses never echo what was submitted. The validation handler keeps `type`, `loc` and `msg` and drops `input`, because FastAPI's default 422 body repeats the rejected value, which would put passwords in response bodies and access logs. `message` is a fixed sentence per status rather than anything derived from the request, so there is no path by which it could start quoting input. Unexpected exceptions return a flat 500 and log the traceback server side, so stack traces and connection strings stay internal.

Request logging follows the same rule. The access line records method, path, status, duration, client IP, correlation ID and the authenticated user id. It never records the body, the query values, or the headers, which is why the template ships no redaction list: nothing is captured that would need one.

Passwords run from 8 to 72 bytes. bcrypt refuses anything longer, so without the ceiling a long passphrase turns into an unhandled 500 on an unauthenticated route.

`SECRET_KEY` must be at least 32 characters and cannot be the example value; the app refuses to start otherwise. `JWT_ALGORITHM` accepts only HS256, HS384 and HS512, so a stray environment variable cannot downgrade token verification.

Addresses are stored in lowercase. `UserCreate` and `UserUpdate` normalize the email before it reaches a service, and login normalizes the submitted username the same way, so `Ada@Example.com` and `ada@example.com` are one account rather than two, and a reader who signs up with the shift key held down can still sign in without it. The migration `0a456e5b983c` lowercases what is already stored; it fails on the partial unique index if two active accounts differ only by case, which is the right outcome, because someone has to decide which one survives.

Request bodies are bounded. `MAX_REQUEST_BODY_BYTES`, 1 MiB by default, is enforced in `app/core/http/body_limit.py`: a declared `Content-Length` above it answers 413 before the route runs, and a body that streams in without one is cut off where it passes the limit. Without that, a single anonymous `POST /api/v1/users` carrying a gigabyte would be read into memory before validation had anything to say about it.

Every response carries `Cache-Control: no-store`. The API answers JSON that is either personal or a token, and no intermediary should keep a copy of either.

CSRF protection is absent deliberately. Authentication is bearer-token only and nothing sets a cookie, so a cross-site request has nothing to ride on. Add it if you introduce cookie sessions. CORS is off by default for the same reason it is safe to leave alone: with no origins allowed, browsers block cross-origin calls. When the frontend lives on another origin, set `CORS_ORIGINS` to a comma-separated list of named origins, and `app/core/http/cors.py` adds `CORSMiddleware` with those origins, no credentials, and `X-Request-ID` in `Access-Control-Expose-Headers`, without which a browser never sees the correlation ID it is meant to show the reader. A `*` in the list refuses to start.

Rate limits on the auth endpoints come from `LOGIN_RATE_LIMIT` and `REGISTER_RATE_LIMIT`; login, refresh, logout and password change share the first. The default limiter counts in memory, so counts reset on restart and are per worker. Point slowapi at Redis before running more than one.

The limiter and the request log both key on the client address, and behind a reverse proxy that address is the proxy's unless uvicorn is told which proxies to believe. Compose starts uvicorn with `--proxy-headers` and passes `FORWARDED_ALLOW_IPS` through, empty by default: with nothing trusted, `X-Forwarded-For` is ignored, so a caller cannot choose its own address to escape the limit. Set it to the proxy's address in production.

Four settings to change before you deploy:

- `HSTS_ENABLED=true`, once TLS terminates in front of the app. It ships off so local HTTP works.
- `DOCS_ENABLED=false`, to withdraw `/docs`, `/redoc` and `/openapi.json`.
- `?ssl=require` appended to `DATABASE_URL`, which asyncpg reads when it connects.
- `FORWARDED_ALLOW_IPS`, set to the reverse proxy's address, so rate limits and the request log see the caller rather than the proxy.

## Feature flags

`FEATURE_FLAGS` names the features reachable in an environment, and `app/core/features.py` turns that list into a dependency:

```python
private_router = APIRouter(
    dependencies=[require_feature(Feature.ITEMS), RequireAuth],
)
```

A flag that is off answers 404, not 403, and the check runs before the token check, so a feature nobody should know about does not announce itself with a 401. `GET /api/v1/features` lists what is on, which is how a frontend decides whether to render a screen at all. It needs a token, because a flag name can describe work nobody has announced yet.

Flags live in the environment because that is the smallest thing that works: no table, no cache, no admin screen. Swapping in a flag service means rewriting `enabled_features` and nothing else.

These flags decide which *endpoints* exist, which is an operator's decision. The frontend keeps a separate list for which *screens* it offers, and an account can override that one for itself through `preferences.features` — a feature preview is a per-person thing, and withdrawing an endpoint is not.

## Preferences

`GET /api/v1/users/me/preferences` and `PATCH` on the same path store a locale, a theme, and whether the frontend should show correlation ids, one row per account in `user_preferences`. The row is written on the first change rather than at registration, so an account that never opens settings costs nothing, and a read with no row returns the defaults.

The API stores the choice; it does not interpret it. `theme` is one of `light`, `dark`, `system`, `locale` is checked against a language-tag pattern rather than a fixed list, and `features` is a comma-separated list of names whose meaning belongs to the frontend — `NULL` means "follow the environment", and an empty string means "none of them". Which languages and which features ship is the frontend's business. A browser will usually keep the same values in `localStorage` for a first paint that does not wait on a request; the table is what makes the choice follow an account to another device.

## Roles and timestamps

Every table except `request_logs` inherits `TimestampMixin` from `app/db/mixins.py`, which supplies `created_at` and an `updated_at` that PostgreSQL refreshes on write. Both come from `now()`, which returns the transaction start time, so a row created and modified inside one transaction carries identical values. They diverge once the writes land in separate transactions, which is what a request per change gives you. A request-log row is never edited, so it carries `created_at` alone.

Permissions live in rows, not in code. A `permissions` row is a `resource` plus an `action`; a `role_permissions` row attaches one of them to a role with a `scope` of `own` or `all`; and `user_roles` attaches roles to accounts. Guard a route with the `require_permission` factory, which hands the route the scope it may read with:

```python
@private_router.get("", dependencies=[require_permission(USERS, READ)])
async def list_users(...): ...
```

A caller without the permission gets 403 and `"detail": "Insufficient permissions"` inside the error envelope, while a caller without a token still gets 401, because the router-level `RequireAuth` runs first.

An account holds any number of roles and the grants add up, with the wider scope winning when two roles name the same permission. `superadmin` is structural: `scope_for` answers `all` for it without reading a grant row, so a resource added later is reachable on the day it ships. Holding no role at all is allowed and means holding no permission — the account still authenticates and reaches `/users/me`, its profile and its preferences, since none of those sit behind `require_permission`. The one removal the API refuses is a superadmin dropping their own `superadmin` role, which would lock the deployment out of its own administration screens.

`POST /api/v1/users/{id}/roles` and `DELETE /api/v1/users/{id}/roles/{name}` work an account's list from the account side; `GET`, `POST /api/v1/roles/{id}/users` and `DELETE /api/v1/roles/{id}/users/{user_id}` work the same rows from the role side. The first account to register on an empty database becomes the superadmin; every later one registers as `user`.

## Tokens

`POST /api/v1/auth/login` returns a short-lived access token and a longer-lived refresh token. `POST /api/v1/auth/refresh` exchanges the refresh token for a fresh pair.

Both tokens carry a `typ` claim, and each decoder insists on its own value. Without that check a refresh token would work as a bearer token on any protected route, which hands back the long lifetime the short access expiry was meant to avoid. The template tests both directions of that confusion.

Refresh tokens are stored, hashed, in `refresh_tokens`, which is what makes them revocable. `POST /api/v1/auth/logout` marks one spent, and changing a password marks every one the account holds. A `jti` claim keeps two logins in the same second from producing the same token, and therefore the same digest.

A refresh does not rotate the token you traded in. The frontend refreshes from two places — its proxy before a render, its API client on a 401 — so rotating would let a concurrent pair race sign a reader out for no reason. The fixed expiry, `REFRESH_TOKEN_EXPIRE_DAYS`, is what bounds a stolen token that nobody has revoked yet.

Access tokens stay stateless: they are checked by signature alone, so revoking a session does not stop an access token already issued until it expires, 30 minutes by default.

Deactivating an account does cut off refreshing straight away, because `refresh` reloads the user and the repository filters soft-deleted rows. For revocation of individual tokens, store them hashed with a `revoked_at` column and check that on refresh.

`POST /api/v1/auth/password` changes a password and answers 204. It re-verifies the current password, because a leaked access token would otherwise be enough to take an account over for good, and it is rate limited with `LOGIN_RATE_LIMIT` since it is an authenticated bcrypt oracle. A wrong current password answers 403 rather than 401: the caller is who they say they are and only failed the step-up, and a frontend that treats 401 as an expired session would sign them out over a typo. It revokes every refresh token the account holds, so other devices have to sign in again; access tokens already minted survive until they expire. Add a `password_changed_at` column and compare `iat` against it if you need that half hour closed too.

`PATCH /api/v1/users/me` updates the display name and the address, answering 409 when the address is taken.

## Soft delete

`DELETE /api/v1/items/{id}` and `DELETE /api/v1/users/me` stamp `deleted_at` instead of removing rows, so the history survives an accidental delete. Repositories filter on `deleted_at IS NULL`, which is written out in each query rather than installed as a global loader rule, because a query that quietly rewrites itself is hard to reason about in a template you are about to copy.

Two details are easy to get wrong:

- A plain unique constraint on `email` would keep a deactivated address reserved forever, so the address becomes unusable rather than free. The template uses a partial unique index instead, `unique on (email) where deleted_at is null`, which still rejects two active accounts on one address while letting a deactivated one register again.
- `User.items` cascades with `all, delete-orphan`, which deletes rows outright. So deactivating an account retires its items through `ItemService.delete_all_for_owner` before the user row is stamped, and the ORM cascade stays reserved for a real hard delete.

Deactivation ends access immediately: `get_by_email` and `get` both filter deleted rows, so a deactivated account cannot log in and an already issued token stops working on the next request.

## Quickstart with Docker

Requires Docker with Compose. Generate a secret first, because the app refuses to start without one:

```bash
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
docker compose up --build
```

Compose starts PostgreSQL, waits for it to pass its healthcheck, applies migrations, and serves the API on http://127.0.0.1:8000. The test database is created alongside the main one by `scripts/create-test-database.sh`. Override `POSTGRES_PORT` or `API_PORT` if those ports are already taken on your machine. The database port is published on loopback only, because the default password is in this file.

A `psql` against that database is one command away, and it needs nothing installed on the host:

```bash
docker compose run --rm psql
docker compose run --rm psql -c 'select count(*) from users'
```

The `psql` service sits behind the `tools` profile, so `docker compose up` does not start it.

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

Create the database role and databases (adjust names/password to taste, then keep `.env` in sync):

```bash
sudo -u postgres psql \
  -c "CREATE ROLE fastapi_user LOGIN PASSWORD 'secret123' CREATEDB;" \
  -c "CREATE DATABASE fastapi_db OWNER fastapi_user;" \
  -c "CREATE DATABASE fastapi_db_test OWNER fastapi_user;"
```

The role needs `CREATEDB` because the migration check in `tests/integration/test_migration_drift.py` provisions a throwaway database, applies every migration to it, and compares the result against the models.

Apply migrations:

```bash
uv run alembic upgrade head
```

## Run the dev server

```bash
uv run fastapi dev app/main.py
```

Open http://127.0.0.1:8000/docs for the interactive API.

That binds loopback only, which is right for development and wrong for a Prometheus running in a container: it reaches the host through the Docker gateway, a different interface, so the target shows as down while `curl` from your shell works perfectly. Bind every interface when you want the metrics scraped:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Observability

Every request carries a correlation ID, and every log line is one JSON object that includes it. Given an ID, you can reconstruct what happened to a request instead of reproducing it.

The `X-Request-ID` header drives it. A caller that sends one keeps it, which is how a frontend stitches its own logs to the API's; a caller that sends nothing gets a fresh `uuid4().hex`. Either way the ID comes back on the response, so a browser can show it on an error screen. Inbound values are checked against `[A-Za-z0-9_-]{1,64}` and replaced when they fail, because a header is untrusted input and a newline in it would forge log lines.

The ID lives in a `ContextVar`, so no logging call has to pass it around. A structlog processor copies it onto every event, including the ones uvicorn writes:

```json
{"method":"GET","path":"/api/v1/items","status_code":401,"duration_ms":4.116,"client_ip":"127.0.0.1","user_id":null,"event":"request","request_id":"verify-e2e-001","service":"fastapi-template","level":"info","logger":"app.request","timestamp":"2026-08-20T20:12:23.962813Z"}
```

`LOG_FORMAT=console` swaps the JSON for a readable stream while you work. `REQUEST_LOG_EXCLUDED_PATHS` keeps probes and scrapes out of the log; the defaults cover `/health`, `/health/ready` and `/metrics`.

### The request log table

The same line is also written to `request_logs`, one row per request, so a frontend can list correlation IDs with an outcome next to each — success under 400, warning in the 4xx range, error at 500 and above — without a Loki query. `GET /api/v1/requests` pages through them and `GET /api/v1/requests/{request_id}` reads one. An admin sees every row; anyone else is scoped to their own, silently, so the endpoint never confirms whose IDs exist. Filters are `outcome`, a `path` prefix, `request_id`, and a `since`/`until` window.

Unauthenticated requests are stored with a null user, which is also what a failed login is, so a normal account cannot see its own 401s — only an admin can. The row it cannot see carries a client IP, which is why it is scoped that way.

The write happens after the response is sent, on its own session, because by then the request's own transaction has already committed or rolled back. A failed insert is logged and swallowed: an audit row must never turn a served response into a 500. That means the structlog line, not the table, is the record of last resort.

It costs one INSERT and three index updates per request: `request_id` for the lookup, `created_at` for the ordering and the window, and `(user_id, created_at)` for a single account's listing. A `status_code` index was dropped deliberately — ten distinct values barely narrow anything, and it was a fourth write on the busiest table here. Add `(status_code, created_at)` if listing errors alone ever gets slow. `REQUEST_LOG_PERSIST_ENABLED=false` withdraws it and leaves everything else working. Rows are deleted by hand or by cron:

```bash
uv run python scripts/prune-request-log.py 30    # keep 30 days
```

It deletes in batches of 5000 and commits between them, so a retention run does not hold one lock for the length of a single enormous statement, and it sweeps expired refresh tokens on the way out.

Past a few million rows, partition by month and drop whole partitions instead.

This is the one collection that does not return a `total`. `GET /api/v1/requests` answers with a `CursorPage` — `items`, `limit`, `next_cursor` — because counting every matching row is what makes a table that grows by one row per request expensive to read, and an `offset` deep into it costs the same walk. The cursor is the ordering key `(created_at, id)`, base64 of the pair, so a row cannot shift under a reader because newer rows arrived above it. The endpoint reads one row past the limit to decide whether to hand back a cursor at all. Every other collection keeps `Page[T]` and its `total`: they are bounded, and a count over a few thousand rows is free. And bear in mind that only the auth routes are throttled, so a flood anywhere else writes rows at the attacker's pace: widen `REQUEST_LOG_EXCLUDED_PATHS`, or sample, before exposing this to the open internet.

Prometheus metrics are served at `/metrics`, from `prometheus-fastapi-instrumentator`. Set `METRICS_ENABLED=false` to withdraw the route. The counters live in the process, so behind more than one worker each reports only its own share, the same caveat the in-memory rate limiter carries.

`GET /api/v1/features` lists what is on, and it needs a token: a flag name can describe work nobody has announced.

### The audit log table

`request_logs` answers who called what. `audit_logs` answers what changed, and from what. One row per mapped insert, update or delete, with the old and new value of every column that moved.

Nothing calls it. The rows are produced by SQLAlchemy session events registered on `Session` itself, so a service cannot forget to record a change — `before_flush` reads the attribute history while the old values are still in memory, `after_flush_postexec` resolves the keys the database just assigned, and the rows go in through Core on the connection the flush is already holding. That last part is why there is no recursion to guard against: the audit rows never enter the unit of work, so nothing sees them on the next flush.

They are written inside the request's own transaction, which is the opposite of the choice `request_logs` makes, and deliberately so. A missing access-log line costs a line of telemetry; a missing audit row costs the record of a change that happened. If the insert fails, the request fails with it.

Four tables stay out: `audit_logs` itself, `request_logs`, `refresh_tokens`, and `alembic_version`. Token rows churn on every login and say nothing a login does not. `hashed_password` and `token_hash` record *that* they changed and never what to — both sides read `***`. `created_at` and `updated_at` never appear: one is a server default and the other an `onupdate` expression, so neither has history anybody typed.

Many-to-many links are covered. `user_roles` is a bare `Table`, but its inserts and deletes travel through `User.roles`, so the listener reads the collection history and files them as `link` and `unlink` with the role's name beside its key. A soft delete is filed as `soft_delete` rather than an ordinary update, and clearing `deleted_at` is a `restore`.

`GET /api/v1/audit` pages through the trail and `GET /api/v1/audit/{id}` reads one, both behind `audit_log:read`, which only `superadmin` holds out of the box. A reader with `Scope.OWN` is pinned to their own rows, silently, the same way the request log narrows. Filters are `table_name`, `row_pk`, `action`, `actor_id`, `impersonator_id`, `request_id` and a `since`/`until` window; the `request_id` is the join back to `request_logs`. It is a `CursorPage` for the same reason the request log is.

A value over 1000 characters is stored as its length rather than its contents, and a diff over 64 KB collapses to the list of field names with `truncated` set — an `items.description` can hold a megabyte, and a diff carries it twice.

Retention is a cron job, the same shape as the request log's:

```bash
uv run python scripts/prune-audit-log.py 365    # keep a year
```

What it does not see is worth knowing. A Core-level `update()` or `delete()` bypasses the unit of work entirely, so the template refuses one against an audited table and names the table in the error; load the rows and change them through the session, or say `with audit_suppressed():` when the statement really is maintenance. Rows removed by a database-level `ON DELETE CASCADE` are deleted by PostgreSQL, not by the ORM, and `op.execute` in a migration produces no events at all. If "every mutation" ever has to be literal rather than "every mutation that goes through our services", the answer is a trigger reading `current_setting('app.actor_id', true)`, and the cost is redaction logic in PL/pgSQL.

### Searching the logs

This template writes the logs and serves the metrics. Storing and searching them is somebody else's job, because one Loki per project also means one Grafana per project, and two queries every time an ID crosses a service boundary.

The companion `devstack` repository runs Loki, Grafana, Alloy and Prometheus once for every project on the machine. Two settings connect this app to it:

```bash
SERVICE_NAME=my-api                                   # unique per app; it is the filter
LOG_FILE=$HOME/.local/state/devlogs/my-api.jsonl      # where Alloy looks
```

Then register the metrics endpoint by dropping one file into that repository's `prometheus/targets/`. Its README has the details.

Under compose the log file is unnecessary: the `api` service already carries a `devstack.service` label, which is how that stack decides whose container stdout to read.

Without `devstack` everything still works: the JSON goes to stdout, and `docker compose logs api | jq 'select(.request_id == "…")'` answers the same question with more typing.

## Test-driven development

The suite runs against a real PostgreSQL test database (`TEST_DATABASE_URL`), wrapping each test in a transaction it rolls back afterwards, so tests stay isolated without rebuilding the schema between them. The schema is created once per session with `Base.metadata.create_all`; Alembic remains the source of truth for the real database.

Red → green → refactor:

1. Write a failing test under `tests/unit` (logic against the typed fakes in `tests/unit/fakes.py`) or `tests/integration` (routes through the test DB).
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

Changing a model without generating a migration fails the suite. The check applies every migration to a fresh database and diffs the result against `Base.metadata`, so the two cannot drift apart silently.

## Changelog and releases

`CHANGELOG.md` is generated from Conventional Commits with [git-cliff](https://git-cliff.org):

```bash
uv run git-cliff --output CHANGELOG.md
```

Regenerate it when you cut a release rather than on every merge. `scripts/check-commit-messages.sh` checks that subjects carry a valid type, which is all the generator needs.

The file tracks changes to the template itself. Clear it when you start a project from this repository, since the history belongs to the template rather than your service.

## Quality tooling

```bash
uv run pre-commit install     # enable hooks (once)
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy app tests         # type-check
uv run pytest --cov           # tests with coverage (fails under 90%)
uv run pip-audit              # known vulnerabilities in dependencies
```

There is no CI workflow, so the hooks are the gate: `uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push` puts ruff and mypy on every commit, `scripts/check-commit-messages.sh` on every commit message, and the whole suite on every push, with `pip-audit` added to the push whenever `pyproject.toml` or `uv.lock` changed.

`CONTRIBUTING.md` covers the workflow. `SECURITY.md` covers how to report a vulnerability and what to change before deploying.

## Project layout

```
app/
  main.py                 # app factory; lifespan, routers, exception handlers
  core/                   # config, security, domain exceptions, feature flags
    http/                 # error envelope, security headers, CORS, body limit, rate limit
    observability/        # logging, correlation ids, access log, metrics
  db/                     # declarative base, engine and session lifecycle
  api/
    deps.py               # shared dependencies (session, current user, services)
    request_recorder.py   # writes the access log row on its own session
    v1/
      router.py           # aggregates v1 routers, public ones first
      routes/             # auth, users, items, requests, features
  models/                 # SQLAlchemy models
  schemas/                # Pydantic schemas, including pagination and the error envelope
  repositories/           # database access
  services/               # business logic
    protocols.py          # repository interfaces the services depend on
alembic/                  # migration environment + versions
scripts/                  # database bootstrap, commit lint, request-log pruning
tests/
  unit/                   # logic against typed fakes
  integration/            # routes through the test database
Dockerfile                # multi-stage build, non-root runtime
compose.yaml              # PostgreSQL + API, migrations on start
CONTRIBUTING.md           # setup, conventions, release sequence
SECURITY.md               # reporting, posture, pre-deploy checklist
```
