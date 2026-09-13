from datetime import timedelta
from functools import partial

from app.core.config import Settings
from app.core.jobs.scheduler import Job
from app.jobs.maintenance import (
    EXPIRE_TOKENS,
    PRUNE_AUDIT_LOG,
    PRUNE_IDEMPOTENCY_KEYS,
    PRUNE_REQUEST_LOG,
    expire_tokens,
    once_across_replicas,
    prune_audit_log,
    prune_idempotency_keys,
    prune_request_log,
)

DAILY = timedelta(days=1)
HOURLY = timedelta(hours=1)


def maintenance_jobs(settings: Settings) -> list[Job]:
    return [
        Job(
            PRUNE_AUDIT_LOG,
            DAILY,
            partial(
                once_across_replicas,
                PRUNE_AUDIT_LOG,
                partial(
                    prune_audit_log,
                    timedelta(days=settings.audit_log_retention_days),
                ),
            ),
        ),
        Job(
            PRUNE_REQUEST_LOG,
            DAILY,
            partial(
                once_across_replicas,
                PRUNE_REQUEST_LOG,
                partial(
                    prune_request_log,
                    timedelta(days=settings.request_log_retention_days),
                ),
            ),
        ),
        Job(
            PRUNE_IDEMPOTENCY_KEYS,
            HOURLY,
            partial(
                once_across_replicas,
                PRUNE_IDEMPOTENCY_KEYS,
                partial(
                    prune_idempotency_keys,
                    timedelta(hours=settings.idempotency_retention_hours),
                ),
            ),
        ),
        Job(
            EXPIRE_TOKENS,
            HOURLY,
            partial(once_across_replicas, EXPIRE_TOKENS, expire_tokens),
        ),
    ]
