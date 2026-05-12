"""ORM-модели. Импорт всех моделей здесь нужен Alembic-у для автогенерации."""

from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.auth_attempt import AuthAttempt
from app.models.base import Base
from app.models.client import Client
from app.models.contract import Contract
from app.models.document_template import DocumentTemplate
from app.models.egrn_extract import EgrnExtract
from app.models.generated_document import GeneratedDocument
from app.models.guarantee_letter import GuaranteeLetter
from app.models.incoming_webhook import IncomingWebhook
from app.models.invitation import Invitation
from app.models.payment_document import PaymentDocument
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.stored_file import StoredFile
from app.models.user import User
from app.models.user_session import UserSession
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription

__all__ = [
    "Address",
    "AddressPhoto",
    "Application",
    "ApplicationEvent",
    "AuthAttempt",
    "Base",
    "Client",
    "Contract",
    "DocumentTemplate",
    "EgrnExtract",
    "GeneratedDocument",
    "GuaranteeLetter",
    "IncomingWebhook",
    "Invitation",
    "PaymentDocument",
    "Provider",
    "ProviderConnectionRequest",
    "StoredFile",
    "User",
    "UserSession",
    "WebhookDelivery",
    "WebhookSubscription",
]
