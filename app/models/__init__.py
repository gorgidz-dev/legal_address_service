"""ORM-модели. Импорт всех моделей здесь нужен Alembic-у для автогенерации."""
from app.models.base import Base
from app.models.user import User
from app.models.provider import Provider
from app.models.address import Address
from app.models.egrn_extract import EgrnExtract
from app.models.client import Client
from app.models.application import Application
from app.models.contract import Contract
from app.models.guarantee_letter import GuaranteeLetter
from app.models.document_template import DocumentTemplate
from app.models.generated_document import GeneratedDocument

__all__ = [
    "Base",
    "User",
    "Provider",
    "Address",
    "EgrnExtract",
    "Client",
    "Application",
    "Contract",
    "GuaranteeLetter",
    "DocumentTemplate",
    "GeneratedDocument",
]
