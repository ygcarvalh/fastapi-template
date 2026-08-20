# Security

## Reporting a vulnerability

Open a private security advisory through GitHub rather than a public issue. Only the latest tag and the current `main` receive fixes; this is a template, so older tags are snapshots of what you already copied.

## What the template already does

`pip-audit` runs in CI against the locked dependency set and fails the build on any known advisory. Dependabot opens weekly pull requests for uv, GitHub Actions, and Docker, and every action in `.github/workflows` is pinned to a commit SHA rather than a moving tag, so a compromised tag cannot silently change what CI executes.

Routes are private by default. `app/api/v1/router.py` includes a `public_router` and a `private_router` per module, and the private one carries `dependencies=[RequireAuth]`, so every route inside it needs a valid bearer token whether or not the handler asks for `CurrentUser`. Forgetting to protect a route is caught rather than shipped: `tests/integration/test_route_policy.py` reads the OpenAPI schema and fails when a route is neither protected nor named in `PUBLIC_OPERATIONS`.

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`, with `Strict-Transport-Security` added when `HSTS_ENABLED` is on. All of them are defined once in `app/core/middleware.py` and asserted in `tests/integration/test_security_headers.py`, so dropping one fails the suite.

Login does not reveal whether an account exists. `AuthService.authenticate` verifies the submitted password against a cached dummy hash when the address is unknown, so a wrong password and an unknown address both pay for a full bcrypt verification and return the same 401. Remove that dummy hash and the two paths diverge by roughly 300 ms, which is enough to enumerate the user table over the network.

Passwords are bounded to 8 through 72 bytes in `app/schemas/user.py`, measured on the encoded bytes rather than the character count. bcrypt refuses anything longer, so without the ceiling a long passphrase becomes an unhandled 500 on an unauthenticated route.

`SECRET_KEY` must be at least 32 characters and cannot be left as the `.env.example` placeholder; the app refuses to start otherwise. `JWT_ALGORITHM` accepts only HS256, HS384, and HS512, so a stray environment variable cannot downgrade token verification.

Access and refresh tokens both carry a `typ` claim, and each decoder in `app/core/security.py` insists on its own value. Without that check a refresh token would work as a bearer token on any protected route, handing back the long lifetime the short access expiry was meant to avoid.

Error responses never echo what was submitted. The validation handler in `app/core/exceptions.py` keeps `type`, `loc`, and `msg` and drops `input`, because FastAPI's default 422 body repeats the rejected value, which would put passwords into response bodies and access logs. Unexpected exceptions return a flat 500 and log the traceback server side, so stack traces and connection strings stay internal.

An inbound `X-Request-ID` is filtered before it reaches a log line. `app/core/request_context.py` accepts at most 64 characters of `[A-Za-z0-9_-]` and mints a fresh ID for anything else, because the header is caller-controlled and a newline in it would let that caller write forged entries into the log stream.

Request logs record metadata only. The access line in `app/core/observability.py` carries method, path, status, duration, client IP, correlation ID, and the authenticated user id. Bodies, query values, and headers never reach it. That is deliberate: a redaction list is the kind of thing nobody remembers to update, and there is nothing here for one to cover.

Deactivation ends access immediately. Repositories filter `deleted_at IS NULL`, so a soft-deleted account cannot log in, its already issued access token stops working on the next request, and its refresh token stops working because `AuthService.refresh` reloads the user. The partial unique index `unique on (email) where deleted_at is null` still rejects two active accounts on one address while letting a deactivated address register again.

CSRF protection is absent deliberately. Authentication is bearer-token only and nothing sets a cookie, so a cross-site request has nothing to ride on. CORS is unconfigured for the same reason it is safe to leave alone: with no origins allowed, browsers block cross-origin calls by default.

The container runs as an unprivileged user. The runtime stage in `Dockerfile` creates a system account with UID 1001 and switches to it before the entrypoint, and the build dependencies stay behind in the builder stage.

## What you must change before deploying

Generate a real `SECRET_KEY` for each environment with `openssl rand -hex 32`, and do not reuse one across environments. Every access and refresh token is signed with it, so sharing it between staging and production means a staging token authenticates in production.

Then work through the following:

- Set `DOCS_ENABLED=false` to withdraw `/docs`, `/redoc`, and `/openapi.json`.
- Set `HSTS_ENABLED=true` once TLS terminates in front of the app. It ships off so local HTTP works.
- Append `?ssl=require` to `DATABASE_URL`, which asyncpg reads when it connects.
- Put Redis behind `app/core/rate_limit.py` before running more than one worker. The default slowapi limiter counts in process memory, so counts reset on restart and the effective limit multiplies by the worker count. `LOGIN_RATE_LIMIT` and `REGISTER_RATE_LIMIT` are the only limits configured; the rest of the API is unthrottled.
- Decide whether stateless refresh tokens are acceptable. They cost you revocation: a refresh does not retire the token traded in, and a stolen one stays useful for the whole of `REFRESH_TOKEN_EXPIRE_DAYS`. For per-token revocation, store them hashed with a `revoked_at` column and check it on refresh.
- Registration answers 409 when an address is already taken, which makes it the one place the template leaks account existence. That is a deliberate trade for a usable signup form. Closing it means answering 202 either way and sending a verification email, which needs a mail provider and a tokens table.
- Promote administrators deliberately. New accounts are created as `user`, and `require_role(UserRole.ADMIN)` is the only thing standing between a caller and an admin route.
