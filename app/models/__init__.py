"""ORM-модели. Импорт всех моделей здесь нужен Alembic-у для автогенерации."""

from app.models.address import Address
from app.models.application import Application
from app.models.base import Base
from app.models.client import Client
from app.models.contract import Contract
from app.models.document_template import DocumentTemplate
from app.models.egrn_extract import EgrnExtract
from app.models.generated_document import GeneratedDocument
from app.models.guarantee_letter import GuaranteeLetter
from app.models.invitation import Invitation
from app.models.payment_document import PaymentDocument
from app.models.provider import Provider
from app.models.stored_file import StoredFile
from app.models.user import User
from app.models.user_session import UserSession

__all__ = [
    "Address",
    "Application",
    "Base",
    "Client",
    "Contract",
    "DocumentTemplate",
    "EgrnExtract",
    "GeneratedDocument",
    "GuaranteeLetter",
    "Invitation",
    "PaymentDocument",
    "Provider",
    "StoredFile",
    "User",
    "UserSession",
]
