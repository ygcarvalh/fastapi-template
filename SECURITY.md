# Security

## Reporting a vulnerability

Open a private security advisory through GitHub rather than a public issue. Only the latest tag and the current `main` receive fixes; this is a template, so older tags are snapshots of what you already copied.

## What the template already does

`uv run pip-audit` reports no known vulnerabilities in the locked dependency set as of 2026-09-11. There is no CI workflow, so the pre-push hook runs it whenever `pyproject.toml` or `uv.lock` is part of the push; run it by hand before a release as well. Dependabot opens weekly pull requests for uv and Docker.

The pre-deploy checklist below and the findings of the 2026-09-11 review live in `docs/security-audit-2026-09-11.md`, together with what the review left as standing debt.

Routes are private by default. `app/api/v1/router.py` includes a `public_router` and a `private_router` per module, and the private one carries `dependencies=[RequireAuth]`, so every route inside it needs a valid bearer token whether or not the handler asks for `CurrentUser`. Forgetting to protect a route is caught rather than shipped: `tests/integration/test_route_policy.py` reads the OpenAPI schema and fails when a route is neither protected nor named in `PUBLIC_OPERATIONS`.

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `Cache-Control: no-store`, with `Strict-Transport-Security` added when `HSTS_ENABLED` is on. All of them are defined once in `app/core/middleware.py` and asserted in `tests/integration/test_security_headers.py`, so dropping one fails the suite. `no-store` is there because every body the API answers is either personal data or a token, and neither belongs in a shared cache.

Request bodies are bounded by `MAX_REQUEST_BODY_BYTES`, 1 MiB by default. `app/core/body_limit.py` answers 413 to a declared `Content-Length` above the limit before the route runs, and cuts off a body that streams in without one at the byte where it passes the limit. The refusal carries the usual envelope and correlation ID. This closes the memory exhaustion an unauthenticated `POST /api/v1/users` with an enormous body would otherwise cause, since FastAPI reads the whole body before validation sees it.

Email addresses are lowercased on registration, on profile update, and on login, in `app/schemas/user.py` and `AuthService.authenticate`. Without that, two accounts could differ only by case, and a reader who registered with a capital letter could not sign in without it. Migration `0a456e5b983c` lowercases what is already stored and fails, deliberately, where two active accounts collide.

`POST /auth/logout` is public, because a client whose access token has expired still has to be able to retire its refresh token, and it is throttled with `LOGIN_RATE_LIMIT`, because it is an unauthenticated write.

Login does not reveal whether an account exists. `AuthService.authenticate` verifies the submitted password against a cached dummy hash when the address is unknown, so a wrong password and an unknown address both pay for a full bcrypt verification and return the same 401. Remove that dummy hash and the two paths diverge by roughly 300 ms, which is enough to enumerate the user table over the network.

Passwords are bounded to 8 through 72 bytes in `app/schemas/user.py`, measured on the encoded bytes rather than the character count. bcrypt refuses anything longer, so without the ceiling a long passphrase becomes an unhandled 500 on an unauthenticated route.

`SECRET_KEY` must be at least 32 characters and cannot be left as the `.env.example` placeholder; the app refuses to start otherwise. `JWT_ALGORITHM` accepts only HS256, HS384, and HS512, so a stray environment variable cannot downgrade token verification.

Access and refresh tokens both carry a `typ` claim, and each decoder in `app/core/security.py` insists on its own value. Without that check a refresh token would work as a bearer token on any protected route, handing back the long lifetime the short access expiry was meant to avoid.

Error responses never echo what was submitted. The validation handler in `app/core/exceptions.py` keeps `type`, `loc`, and `msg` and drops `input`, because FastAPI's default 422 body repeats the rejected value, which would put passwords into response bodies and access logs. Unexpected exceptions return a flat 500 and log the traceback server side, so stack traces and connection strings stay internal.

Every error carries `detail`, `message`, and `request_id`. The `message` is a fixed sentence chosen by status, or the domain error's own detail, never anything derived from the request, so a frontend can show it without a second thought about what it might contain. A correlation ID is not a secret: it identifies a request in your logs and grants nothing.

Changing a password re-verifies the current one. A bearer token alone is not enough, because a leaked 30-minute token would otherwise convert into permanent account takeover. The endpoint is rate limited with `LOGIN_RATE_LIMIT`, since it is the one authenticated password check in the API, and it answers 403 rather than 401 on a wrong current password so that a frontend does not read a typo as an expired session. Tokens minted before the change keep working for the rest of their lifetime; add `password_changed_at` and compare `iat` against it if that window matters.

An inbound `X-Request-ID` is filtered before it reaches a log line. `app/core/request_context.py` accepts at most 64 characters of `[A-Za-z0-9_-]` and mints a fresh ID for anything else, because the header is caller-controlled and a newline in it would let that caller write forged entries into the log stream.

Request logs record metadata only. The access line in `app/core/observability.py` carries method, path, status, duration, client IP, correlation ID, and the authenticated user id. Bodies, query values, and headers never reach it. That is deliberate: a redaction list is the kind of thing nobody remembers to update, and there is nothing here for one to cover.

The request log table records metadata only, and the same fields as the log line: method, path without the query string, status, duration, client IP, correlation ID, and the user id when there was one. A secret in a query value therefore never lands in it, though a secret in a path would. Rows are visible to their owner and to an admin, and there is no foreign key on `user_id`, so the trail survives the account it describes. `client_ip` is personal data and retention is the only control over it: set `REQUEST_LOG_RETENTION_DAYS`, schedule `scripts/prune-request-log.py`, or turn the table off with `REQUEST_LOG_PERSIST_ENABLED=false`.

A disabled feature answers 404 before it checks the token. That order matters: a flag guarding an unreleased route should not confirm the route exists to an anonymous caller, and 403 or 401 would.

Preferences store a locale, a theme, and one boolean. The locale is matched against a language-tag pattern rather than stored as sent, because it reaches log lines and HTML attributes; the theme is a fixed set of three.

Deactivation ends access immediately. Repositories filter `deleted_at IS NULL`, so a soft-deleted account cannot log in, its already issued access token stops working on the next request, and its refresh token stops working because `AuthService.refresh` reloads the user. The partial unique index `unique on (email) where deleted_at is null` still rejects two active accounts on one address while letting a deactivated address register again.

CSRF protection is absent deliberately. Authentication is bearer-token only and nothing sets a cookie, so a cross-site request has nothing to ride on. CORS is off by default for the same reason it is safe to leave alone: with no origins allowed, browsers block cross-origin calls. `CORS_ORIGINS` turns it on for a comma-separated list of named origins, with no credentials and `X-Request-ID` exposed so the browser can read the correlation header. A `*` in that list is refused at startup in `app/core/config.py`, because a wildcard would let any site call the API with a token it had stolen.

The client address that the rate limiter and the request log record is the one uvicorn reports. Compose starts uvicorn with `--proxy-headers` and an empty `FORWARDED_ALLOW_IPS`, so `X-Forwarded-For` is ignored until you name the proxy allowed to set it. Trusting it from everywhere would let a caller pick its own address and walk around the limit.

The container runs as an unprivileged user. The runtime stage in `Dockerfile` creates a system account with UID 1001 and switches to it before the entrypoint, and the build dependencies stay behind in the builder stage.

## What you must change before deploying

Generate a real `SECRET_KEY` for each environment with `openssl rand -hex 32`, and do not reuse one across environments. Every access and refresh token is signed with it, so sharing it between staging and production means a staging token authenticates in production.

Then work through the following:

- Set `DOCS_ENABLED=false` to withdraw `/docs`, `/redoc`, and `/openapi.json`.
- Set `HSTS_ENABLED=true` once TLS terminates in front of the app. It ships off so local HTTP works.
- Append `?ssl=require` to `DATABASE_URL`, which asyncpg reads when it connects.
- Set `FORWARDED_ALLOW_IPS` to the reverse proxy's address. Until you do, every caller shares the proxy's address in the rate limiter and the request log, which means one abusive client throttles everyone.
- Set `CORS_ORIGINS` only if the frontend is served from another origin, and name each origin. The sibling frontends put the SPA and `/api` on one origin behind a proxy instead, which needs nothing here.
- Put Redis behind `app/core/rate_limit.py` before running more than one worker. The default slowapi limiter counts in process memory, so counts reset on restart and the effective limit multiplies by the worker count. Login, refresh, logout and password change share `LOGIN_RATE_LIMIT`, registration has `REGISTER_RATE_LIMIT`; the rest of the API is unthrottled.
- Decide whether a refresh should rotate the token. It does not, so a stolen refresh token stays useful until it expires or is revoked by a logout, a password change, or deactivation. Rotation was left out because the frontends refresh from two places and a rotation race would sign readers out at random; if your client refreshes from one place, rotating is a small change to `AuthService.refresh`.
- Decide whether `/metrics` and `/health/ready` may stay public. Neither needs a token: the first lists every route with its latency, the second says whether the database answers. Both are meant for a scraper and a load balancer on the internal network, so keep them off the public listener at the proxy.
- Registration answers 409 when an address is already taken, which makes it the one place the template leaks account existence. That is a deliberate trade for a usable signup form. Closing it means answering 202 either way and sending a verification email, which needs a mail provider and a tokens table.
- Decide whether the request log table is worth its cost here. It writes one row per request, and only the auth routes are rate limited, so an unauthenticated flood on any other path fills it at the attacker's pace. Widen `REQUEST_LOG_EXCLUDED_PATHS`, sample, or set `REQUEST_LOG_PERSIST_ENABLED=false`. Whatever you keep, schedule the pruner and size the connection pool for one extra checkout per request.
- Promote administrators deliberately. New accounts are created as `user`, and `require_role(UserRole.ADMIN)` is the only thing standing between a caller and an admin route.
