from __future__ import annotations

from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.user import User


def _check_constraint_sql(model, name: str) -> str:
    for constraint in model.__table__.constraints:
        if constraint.name == name or constraint.name.endswith(f"_{name}"):
            return str(constraint.sqltext)
    raise AssertionError(f"{name} not found")


def test_user_model_supports_marketplace_roles_and_provider_link() -> None:
    assert "provider_id" in User.__table__.columns
    foreign_key = next(iter(User.__table__.columns.provider_id.foreign_keys))
    assert str(foreign_key.column) == "providers.id"
    assert "'client'" in _check_constraint_sql(User, "role_valid")
    assert "'owner'" in _check_constraint_sql(User, "role_valid")


def test_address_model_has_publication_moderation_columns() -> None:
    for column_name in (
        "publication_status",
        "published_at",
        "moderation_comment",
        "moderated_by",
        "moderated_at",
    ):
        assert column_name in Address.__table__.columns
    assert "'published'" in _check_constraint_sql(Address, "publication_status_valid")


def test_application_status_constraint_accepts_marketplace_statuses() -> None:
    status_constraint = _check_constraint_sql(Application, "status_valid")
    assert "'awaiting_payment'" in status_constraint
    assert "'documents_review'" in status_constraint
    assert "'ready_for_client'" in status_constraint


def test_provider_connection_request_table_shape() -> None:
    columns = ProviderConnectionRequest.__table__.columns
    assert "company_name" in columns
    assert "contact_email" in columns
    assert "status" in columns
    assert "reviewed_by" in columns
    assert "'invited'" in _check_constraint_sql(ProviderConnectionRequest, "status_valid")


def test_application_event_table_shape() -> None:
    columns = ApplicationEvent.__table__.columns
    assert "application_id" in columns
    assert "kind" in columns
    assert "audience" in columns
    assert "is_read" in columns
    assert "'status_changed'" in _check_constraint_sql(ApplicationEvent, "kind_valid")
