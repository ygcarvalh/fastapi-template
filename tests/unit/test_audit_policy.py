from app.core.audit.context import (
    AuditContext,
    audit_suppressed,
    bind_actor,
    current_audit_context,
    is_suppressed,
    set_audit_context,
)
from app.core.audit.listeners import UnauditedBulkMutation
from app.core.audit.policy import is_audited, is_ignored, is_redacted


def test_the_trails_the_template_already_keeps_stay_out_of_this_one() -> None:
    assert not is_audited("audit_logs")
    assert not is_audited("request_logs")
    assert not is_audited("refresh_tokens")
    assert not is_audited("alembic_version")


def test_every_other_table_is_in() -> None:
    assert is_audited("users")
    assert is_audited("user_roles")
    assert is_audited("a_table_added_later")


def test_a_credential_column_is_named_before_it_can_leak() -> None:
    assert is_redacted("hashed_password")
    assert is_redacted("token_hash")
    assert not is_redacted("email")


def test_the_columns_the_database_maintains_are_not_changes_anyone_made() -> None:
    assert is_ignored("created_at")
    assert is_ignored("updated_at")
    assert not is_ignored("deleted_at")


def test_a_refused_bulk_statement_says_which_table_it_would_have_changed() -> None:
    assert "items" in str(UnauditedBulkMutation("items"))


def test_an_actor_binds_onto_the_context_the_request_opened() -> None:
    set_audit_context(AuditContext(request_id="abc"))

    bind_actor(7, impersonator_id=3)

    context = current_audit_context()
    assert context is not None
    assert (context.actor_id, context.impersonator_id) == (7, 3)
    set_audit_context(None)


def test_an_actor_outside_a_request_has_nothing_to_bind_onto() -> None:
    set_audit_context(None)

    bind_actor(7)

    assert current_audit_context() is None


def test_suppression_lasts_exactly_as_long_as_the_block() -> None:
    assert not is_suppressed()

    with audit_suppressed():
        assert is_suppressed()

    assert not is_suppressed()
