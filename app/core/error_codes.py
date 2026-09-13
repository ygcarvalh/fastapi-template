from enum import StrEnum


class ErrorCode(StrEnum):
    UNEXPECTED = "error.unexpected"
    VALIDATION = "error.validation"
    RATE_LIMITED = "error.rateLimited"
    REQUEST_FAILED = "error.requestFailed"
    NOT_FOUND = "error.notFound"
    CONFLICT = "error.conflict"
    UNAUTHORIZED = "error.unauthorized"
    FORBIDDEN = "error.forbidden"
    PAYLOAD_TOO_LARGE = "error.payloadTooLarge"
    PRECONDITION_REQUIRED = "error.preconditionRequired"
    VERSION_CONFLICT = "error.versionConflict"
    IDEMPOTENCY_INVALID_KEY = "idempotency.invalidKey"
    IDEMPOTENCY_BODY_MISMATCH = "idempotency.bodyMismatch"
    IDEMPOTENCY_IN_FLIGHT = "idempotency.inFlight"

    AUTH_INVALID_CREDENTIALS = "auth.invalidCredentials"
    AUTH_BAD_LOGIN = "auth.badLogin"
    AUTH_CURRENT_PASSWORD_INCORRECT = "auth.currentPasswordIncorrect"
    AUTH_IMPERSONATION_SELF = "auth.impersonationSelf"
    AUTH_IMPERSONATION_REVOKED = "auth.impersonationRevoked"
    AUTH_IMPERSONATION_BLOCKED = "auth.impersonationBlocked"
    AUTH_INSUFFICIENT_PERMISSIONS = "auth.insufficientPermissions"
    AUTH_INVALID_TOKEN = "auth.invalidToken"
    AUTH_EMAIL_NOT_VERIFIED = "auth.emailNotVerified"

    ITEM_NOT_FOUND = "item.notFound"
    ATTACHMENT_NOT_FOUND = "attachment.notFound"
    ATTACHMENT_TYPE_REFUSED = "attachment.typeRefused"
    ATTACHMENT_TOO_LARGE = "attachment.tooLarge"

    USER_NOT_FOUND = "user.notFound"
    USER_EMAIL_TAKEN = "user.emailTaken"
    USER_PASSWORD_INCORRECT = "user.passwordIncorrect"
    USER_SELF_ADMIN_ROLE = "user.selfAdminRole"
    USER_CLOSE_OWN_ACCOUNT = "user.closeOwnAccount"

    ROLE_NOT_FOUND = "role.notFound"
    ROLE_NAME_TAKEN = "role.nameTaken"
    ROLE_ADMIN_IMMUTABLE = "role.adminImmutable"
    ROLE_BUILT_IN = "role.builtIn"
    ROLE_HAS_ACCOUNTS = "role.hasAccounts"
    PERMISSION_NOT_FOUND = "permission.notFound"

    REQUEST_LOG_NOT_FOUND = "requestLog.notFound"
    AUDIT_LOG_NOT_FOUND = "auditLog.notFound"
