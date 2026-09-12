# Changelog

All notable changes to this template. Generated from Conventional Commits with [git-cliff](https://git-cliff.org). Clear this file when you start a project from the template.

## 1.1.0 - 2026-09-12

### Bug fixes

- Serve the audit log under compose defaults

### Documentation

- Document the audit trail rules

### Features

- Require the password to close an account
- Add account administration endpoints
- Put access behind roles and permissions
- Assign features and rename the admin role
- Let an account hold several roles
- Gate settings and flags by permission
- Let a role hand down feature flags
- Add the audit log table
- Record mutations from session events
- Expose the audit log API
- Let an admin act as another account
- Let an admin close another account

### Miscellaneous

- Reflow a role service test call
- Drop the comments from the new modules

### Refactoring

- Move the cursor helpers to pagination

## 1.0.0 - 2026-09-11

### Bug fixes

- Normalize email addresses to lowercase
- Rate limit the logout endpoint
- Refresh an item after a partial update

### Documentation

- Describe the security review and new settings

### Features

- Refuse request bodies above a size limit
- Send Cache-Control no-store on responses
- Allow named CORS origins via CORS_ORIGINS

### Miscellaneous

- [fastapi] initial template project
- Add psql service and bind db to loopback
- Wire commit-msg and pip-audit hooks
- Refresh the locked dependency set
- Release v1.0.0

### Refactoring

- Move account use cases into services
- Group core into http and observability
- Fold the email lookup protocol
