from app.core.authorization import BASE_ROLES
from app.core.config import Settings
from app.db.demo import DEMO_USERS


def test_every_demo_email_is_on_the_example_domain() -> None:
    for demo_user in DEMO_USERS:
        assert demo_user.email.endswith("@example.com")


def test_every_demo_email_is_unique() -> None:
    emails = [demo_user.email for demo_user in DEMO_USERS]
    assert len(emails) == len(set(emails))


def test_every_demo_role_is_a_base_role() -> None:
    for demo_user in DEMO_USERS:
        assert demo_user.role in BASE_ROLES


def test_every_demo_attachment_type_is_accepted_by_default() -> None:
    default_types = Settings.model_fields["attachment_content_types"].default.split(",")

    for demo_user in DEMO_USERS:
        for attachment in demo_user.attachments:
            assert attachment.content_type in default_types


def test_every_demo_attachment_belongs_to_one_of_its_users_items() -> None:
    for demo_user in DEMO_USERS:
        titles = {item.title for item in demo_user.items}
        for attachment in demo_user.attachments:
            assert attachment.item_title in titles


def test_at_least_one_demo_item_is_soft_deleted() -> None:
    all_items = [item for demo_user in DEMO_USERS for item in demo_user.items]
    assert any(item.deleted for item in all_items)
