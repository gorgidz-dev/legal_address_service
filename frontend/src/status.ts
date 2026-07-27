/**
 * Единственная карта статусов заявки: подпись, короткая подпись и тон.
 *
 * До этого статус описывался в трёх местах — словарь statusLabels в App.tsx,
 * правила `.status.<status>` в design/app-shell.css и вторая копия тех же
 * правил в styles.css. Наборы разошлись: guarantee_issued и active были
 * зелёными в одном файле и синими в другом, а тон задавался отдельно от
 * подписи, поэтому новый статус попадал в интерфейс без цвета.
 *
 * Тип `Record<ApplicationStatus, StatusMeta>` намеренно полный: пропущенный
 * статус — ошибка компиляции, а не серый бейдж в проде.
 */
import type { ApplicationStatus } from "./types";

export type Tone = "brand" | "info" | "success" | "warning" | "danger" | "neutral";

export type StatusMeta = {
  /** Полная подпись: панель заявки, мобильная карточка, лента. */
  label: string;
  /** Короткая подпись для ячейки таблицы, до 14 символов. */
  short: string;
  tone: Tone;
};

/**
 * Правило тонов:
 *  success — подтверждённый факт или хороший исход;
 *  brand   — ждём действия или денег от клиента, это главный призыв;
 *  info    — процесс идёт, вмешательство не нужно;
 *  warning — нужно действие человека;
 *  danger  — срыв или открытая финансовая проблема, вмешивается оператор;
 *  neutral — пассив и архив.
 *
 * Подписи взяты из прежней карты App.tsx без изменений: этот шаг меняет
 * систему, а не тексты. Расходящаяся карта на бэкенде
 * (app/services/marketplace_status.py) в API не отдаётся и здесь не
 * используется — там ещё доребрендинговый «исполнитель» вместо
 * «собственника».
 */
export const STATUS: Record<ApplicationStatus, StatusMeta> = {
  draft: { label: "Черновик", short: "Черновик", tone: "neutral" },
  guarantee_issued: { label: "Гарантийка выдана", short: "Гарантийка", tone: "info" },
  awaiting_contract: { label: "Ожидает договор", short: "Ждёт договор", tone: "brand" },
  contract_signed: { label: "Договор подписан", short: "Подписан", tone: "success" },
  active: { label: "Активна", short: "Активна", tone: "success" },
  // Срок вышел, но это штатный конец договора с понятным действием «продлить»,
  // а не авария — поэтому warning, а не danger.
  expired: { label: "Истекла", short: "Истекла", tone: "warning" },
  terminated: { label: "Расторгнута", short: "Расторгнута", tone: "danger" },
  awaiting_payment: { label: "Ожидает оплату", short: "Оплата", tone: "brand" },
  paid: { label: "Оплачена", short: "Оплачена", tone: "success" },
  admin_review: { label: "Проверка администратора", short: "Проверка", tone: "info" },
  needs_client_fix: { label: "Нужны уточнения", short: "Правки", tone: "warning" },
  assigned_to_owner: { label: "Передана собственнику", short: "У собственника", tone: "warning" },
  accepted_by_owner: { label: "Принята собственником", short: "Принята", tone: "info" },
  rejected_by_owner: { label: "Отклонена собственником", short: "Отказ", tone: "danger" },
  documents_preparing: { label: "Готовятся документы", short: "Подготовка", tone: "info" },
  documents_uploaded: { label: "Документы загружены", short: "Загружены", tone: "info" },
  documents_review: { label: "Проверка документов", short: "Документы", tone: "info" },
  documents_revision: { label: "Доработка документов", short: "Доработка", tone: "warning" },
  ready_for_client: { label: "Готова к выдаче", short: "Готово", tone: "success" },
  completed: { label: "Завершена", short: "Завершена", tone: "success" },
  // Отмена и возврат — закрытые состояния: вмешиваться уже не во что, красный
  // в очереди оператора должен означать «нужно что-то сделать».
  cancelled: { label: "Отменена", short: "Отменена", tone: "neutral" },
  dispute: { label: "Спор", short: "Спор", tone: "danger" },
  refund_pending: { label: "Возврат готовится", short: "Возврат", tone: "danger" },
  refunded: { label: "Возврат выполнен", short: "Возвращено", tone: "neutral" }
};

/**
 * Статус может прийти из базы значением, которого нет в карте (старая запись,
 * рассинхрон с бэкендом). Пустая ячейка в таблице хуже сырого кода — поэтому
 * фолбэк показывает само значение.
 */
export function statusMeta(status: string | null | undefined): StatusMeta {
  if (status && status in STATUS) return STATUS[status as ApplicationStatus];
  const raw = status || "—";
  return { label: raw, short: raw, tone: "neutral" };
}

export function statusLabel(status: string | null | undefined): string {
  return statusMeta(status).label;
}
