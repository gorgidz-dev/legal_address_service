from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationEventKind, ApplicationStatus, NotificationAudience, UserRole
from app.models.application import Application
from app.models.user import User
from app.schemas.workflow import ApplicationActionResult
from app.services.marketplace_status import role_actions_for_status
from app.services.notification_events import create_application_event


@dataclass(frozen=True)
class WorkflowEventTemplate:
    audience: NotificationAudience
    title: str
    message: str


@dataclass(frozen=True)
class WorkflowTransition:
    target_status: ApplicationStatus
    next_action_role: UserRole | None
    event_kind: ApplicationEventKind
    events: tuple[WorkflowEventTemplate, ...]


def _event(audience: NotificationAudience, title: str, message: str) -> WorkflowEventTemplate:
    return WorkflowEventTemplate(audience=audience, title=title, message=message)


_TRANSITIONS: dict[tuple[UserRole, ApplicationStatus, str], WorkflowTransition] = {
    (
        UserRole.ADMIN,
        ApplicationStatus.PAID,
        "start_admin_review",
    ): WorkflowTransition(
        target_status=ApplicationStatus.ADMIN_REVIEW,
        next_action_role=UserRole.ADMIN,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка взята в проверку", "Администратор начал ручную проверку заявки."),
            _event(NotificationAudience.CLIENT, "Заявка на проверке", "Мы проверяем данные и адрес по заявке."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.ADMIN_REVIEW,
        "assign_owner",
    ): WorkflowTransition(
        target_status=ApplicationStatus.ASSIGNED_TO_OWNER,
        next_action_role=UserRole.OWNER,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка передана исполнителю", "Администратор назначил заявку собственнику."),
            _event(NotificationAudience.OWNER, "Заявка передана исполнителю", "Администратор назначил заявку на ваш адрес."),
            _event(NotificationAudience.CLIENT, "Заявка передана собственнику", "Собственник получил заявку и проверит возможность подготовки документов."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.ADMIN_REVIEW,
        "request_client_fix",
    ): WorkflowTransition(
        target_status=ApplicationStatus.NEEDS_CLIENT_FIX,
        next_action_role=UserRole.CLIENT,
        event_kind=ApplicationEventKind.CORRECTION_REQUESTED,
        events=(
            _event(NotificationAudience.ADMIN, "Запрошены уточнения клиента", "Заявка возвращена клиенту на уточнение данных."),
            _event(NotificationAudience.CLIENT, "Нужны уточнения по заявке", "Администратор просит уточнить данные перед передачей заявки исполнителю."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.ADMIN_REVIEW,
        "cancel",
    ): WorkflowTransition(
        target_status=ApplicationStatus.CANCELLED,
        next_action_role=None,
        event_kind=ApplicationEventKind.CANCELLED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка отменена", "Администратор отменил заявку на этапе проверки."),
            _event(NotificationAudience.CLIENT, "Заявка отменена", "Заявка отменена после проверки администратором."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.REJECTED_BY_OWNER,
        "assign_owner",
    ): WorkflowTransition(
        target_status=ApplicationStatus.ASSIGNED_TO_OWNER,
        next_action_role=UserRole.OWNER,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка повторно передана исполнителю", "Администратор вернул заявку в работу исполнителя."),
            _event(NotificationAudience.OWNER, "Заявка передана исполнителю", "Администратор повторно назначил заявку на ваш адрес."),
            _event(NotificationAudience.CLIENT, "Заявка снова передана собственнику", "Площадка повторно передала заявку собственнику."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.REJECTED_BY_OWNER,
        "cancel",
    ): WorkflowTransition(
        target_status=ApplicationStatus.CANCELLED,
        next_action_role=None,
        event_kind=ApplicationEventKind.CANCELLED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка отменена", "Администратор отменил заявку после отказа исполнителя."),
            _event(NotificationAudience.CLIENT, "Заявка отменена", "Заявка отменена после проверки доступности адреса."),
            _event(NotificationAudience.OWNER, "Заявка отменена", "Заявка отменена площадкой после отказа исполнителя."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.DOCUMENTS_REVIEW,
        "approve_documents",
    ): WorkflowTransition(
        target_status=ApplicationStatus.READY_FOR_CLIENT,
        next_action_role=UserRole.CLIENT,
        event_kind=ApplicationEventKind.DOCUMENT_APPROVED,
        events=(
            _event(NotificationAudience.ADMIN, "Документы одобрены", "Администратор одобрил комплект документов."),
            _event(NotificationAudience.OWNER, "Документы одобрены", "Комплект документов прошёл проверку площадки."),
            _event(NotificationAudience.CLIENT, "Документы готовы", "Комплект документов готов к получению в личном кабинете."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.DOCUMENTS_REVIEW,
        "request_document_revision",
    ): WorkflowTransition(
        target_status=ApplicationStatus.DOCUMENTS_REVISION,
        next_action_role=UserRole.OWNER,
        event_kind=ApplicationEventKind.CORRECTION_REQUESTED,
        events=(
            _event(NotificationAudience.ADMIN, "Документы отправлены на доработку", "Администратор запросил исправления в комплекте документов."),
            _event(NotificationAudience.OWNER, "Нужна доработка документов", "Администратор вернул комплект документов на доработку."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.DISPUTE,
        "resolve_dispute",
    ): WorkflowTransition(
        target_status=ApplicationStatus.READY_FOR_CLIENT,
        next_action_role=UserRole.CLIENT,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.ADMIN, "Спор урегулирован", "Заявка возвращена к выдаче документов клиенту."),
            _event(NotificationAudience.CLIENT, "Спор урегулирован", "Заявка снова готова к получению документов."),
            _event(NotificationAudience.OWNER, "Спор урегулирован", "Площадка закрыла спор по заявке."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.DISPUTE,
        "cancel",
    ): WorkflowTransition(
        target_status=ApplicationStatus.CANCELLED,
        next_action_role=None,
        event_kind=ApplicationEventKind.CANCELLED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка отменена", "Администратор отменил спорную заявку."),
            _event(NotificationAudience.CLIENT, "Заявка отменена", "Площадка отменила заявку после рассмотрения спора."),
            _event(NotificationAudience.OWNER, "Заявка отменена", "Площадка отменила заявку после рассмотрения спора."),
        ),
    ),
    (
        UserRole.ADMIN,
        ApplicationStatus.DISPUTE,
        "complete",
    ): WorkflowTransition(
        target_status=ApplicationStatus.COMPLETED,
        next_action_role=None,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.ADMIN, "Заявка завершена", "Администратор завершил заявку после рассмотрения спора."),
            _event(NotificationAudience.CLIENT, "Заявка завершена", "Заявка закрыта площадкой после рассмотрения спора."),
            _event(NotificationAudience.OWNER, "Заявка завершена", "Заявка закрыта площадкой после рассмотрения спора."),
        ),
    ),
    (
        UserRole.OWNER,
        ApplicationStatus.ASSIGNED_TO_OWNER,
        "accept",
    ): WorkflowTransition(
        target_status=ApplicationStatus.ACCEPTED_BY_OWNER,
        next_action_role=UserRole.OWNER,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.OWNER, "Заявка принята", "Вы приняли заявку в работу."),
            _event(NotificationAudience.ADMIN, "Исполнитель принял заявку", "Собственник подтвердил готовность работать с заявкой."),
            _event(NotificationAudience.CLIENT, "Собственник принял заявку", "Собственник подтвердил адрес и начал подготовку."),
        ),
    ),
    (
        UserRole.OWNER,
        ApplicationStatus.ASSIGNED_TO_OWNER,
        "reject",
    ): WorkflowTransition(
        target_status=ApplicationStatus.REJECTED_BY_OWNER,
        next_action_role=UserRole.ADMIN,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.OWNER, "Заявка отклонена", "Вы отклонили заявку."),
            _event(NotificationAudience.ADMIN, "Исполнитель отклонил заявку", "Нужно назначить другой адрес или связаться с собственником."),
            _event(NotificationAudience.CLIENT, "Заявка требует переназначения", "Площадка подберет другой адрес или уточнит детали."),
        ),
    ),
    (
        UserRole.OWNER,
        ApplicationStatus.ACCEPTED_BY_OWNER,
        "start_documents",
    ): WorkflowTransition(
        target_status=ApplicationStatus.DOCUMENTS_PREPARING,
        next_action_role=UserRole.OWNER,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.OWNER, "Подготовка документов началась", "Вы перевели заявку в подготовку документов."),
            _event(NotificationAudience.ADMIN, "Исполнитель готовит документы", "Собственник начал подготовку комплекта документов."),
            _event(NotificationAudience.CLIENT, "Документы готовятся", "Собственник начал подготовку комплекта документов."),
        ),
    ),
    (
        UserRole.CLIENT,
        ApplicationStatus.NEEDS_CLIENT_FIX,
        "submit_corrections",
    ): WorkflowTransition(
        target_status=ApplicationStatus.ADMIN_REVIEW,
        next_action_role=UserRole.ADMIN,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.CLIENT, "Уточнения отправлены", "Заявка снова передана на проверку администратору."),
            _event(NotificationAudience.ADMIN, "Клиент отправил уточнения", "Проверьте обновленные данные по заявке."),
        ),
    ),
    (
        UserRole.CLIENT,
        ApplicationStatus.READY_FOR_CLIENT,
        "confirm_received",
    ): WorkflowTransition(
        target_status=ApplicationStatus.COMPLETED,
        next_action_role=None,
        event_kind=ApplicationEventKind.STATUS_CHANGED,
        events=(
            _event(NotificationAudience.CLIENT, "Получение подтверждено", "Вы подтвердили получение документов."),
            _event(NotificationAudience.ADMIN, "Клиент подтвердил получение", "Клиент подтвердил получение документов по заявке."),
            _event(NotificationAudience.OWNER, "Клиент подтвердил получение", "Клиент подтвердил получение документов по заявке."),
        ),
    ),
    (
        UserRole.CLIENT,
        ApplicationStatus.READY_FOR_CLIENT,
        "open_dispute",
    ): WorkflowTransition(
        target_status=ApplicationStatus.DISPUTE,
        next_action_role=UserRole.ADMIN,
        event_kind=ApplicationEventKind.DISPUTE_OPENED,
        events=(
            _event(NotificationAudience.CLIENT, "Открыт спор", "Спор передан администратору площадки."),
            _event(NotificationAudience.ADMIN, "Клиент открыл спор", "Проверьте заявку и документы."),
            _event(NotificationAudience.OWNER, "Клиент открыл спор", "Площадка проверит спор по заявке."),
        ),
    ),
}


def workflow_role_for_user(user: User | object) -> UserRole:
    try:
        role = UserRole(getattr(user, "role"))
    except ValueError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для действия") from e

    if role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER}:
        return UserRole.ADMIN
    return role


def next_actions_for_status(status_value: ApplicationStatus | str, role: UserRole | None) -> list[str]:
    if role is None:
        return []
    return role_actions_for_status(role, status_value)


def _ensure_user_can_access_application(user: User | object, role: UserRole, application: Application) -> None:
    if role == UserRole.OWNER:
        if getattr(user, "provider_id", None) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя")
        if application.provider_id != getattr(user, "provider_id"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Заявка назначена другому исполнителю")
    if role == UserRole.CLIENT and application.created_by != getattr(user, "id", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Заявка принадлежит другому клиенту")


async def apply_application_action(
    *,
    db: AsyncSession,
    application_id: UUID,
    action: str,
    user: User | object,
) -> ApplicationActionResult:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")

    role = workflow_role_for_user(user)
    _ensure_user_can_access_application(user, role, application)

    current_status = ApplicationStatus(application.status)
    transition = _TRANSITIONS.get((role, current_status, action))
    if transition is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Недоступное действие `{action}` для статуса `{current_status.value}`",
        )

    previous_status = current_status
    application.status = transition.target_status.value

    payload = {
        "action": action,
        "previous_status": previous_status.value,
        "status": transition.target_status.value,
    }
    created_by = getattr(user, "id", None)

    for event in transition.events:
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=transition.event_kind,
            audience=event.audience,
            title=event.title,
            message=event.message,
            payload=payload,
            created_by=created_by,
        )

    await db.flush()
    return ApplicationActionResult(
        application_id=application.id,
        status=transition.target_status,
        available_actions=next_actions_for_status(transition.target_status, transition.next_action_role),
    )
