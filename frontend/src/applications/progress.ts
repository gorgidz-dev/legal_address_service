/**
 * Прогресс заявки шестью шагами: Оплата → Проверка → Собственник → Документы →
 * Расписка → Регистрация (этап 6 дорожной карты, статус-трекер).
 *
 * Нужен, чтобы не заставлять читать ленту событий ради ответа на вопрос «где
 * сейчас моя заявка». Первые четыре шага считаются из статуса. Последние два —
 * после выдачи документов, из фактов заявки: загружена ли расписка ИФНС и
 * подтвердила ли площадка регистрацию по ЕГРЮЛ. Раньше пятым шагом было «Готово»
 * — оно значило лишь «документы выданы», хотя клиенту важна сама регистрация.
 */
import type { ApplicationStatus } from "../types";

export const STEPS = ["Оплата", "Проверка", "Собственник", "Документы", "Расписка", "Регистрация"] as const;

/** Факты трекера после выдачи документов (поля заявки с бэкенда). */
export type TrackerFacts = {
  ifns_receipt_uploaded_at?: string | null;
  registration_expected_on?: string | null;
  registration_confirmed_at?: string | null;
};

const DOCUMENTS_ISSUED = new Set(["ready_for_client", "completed"]);

/**
 * Шаг, на котором заявка стоит сейчас. `null` — заявка вне основной цепочки:
 * отменена, в споре, на возврате или это старый договорной поток. Рисовать для
 * них полоску нельзя — она показывала бы движение вперёд там, где его нет.
 */
export function currentStep(status: ApplicationStatus | string, facts: TrackerFacts = {}): number | null {
  switch (status) {
    case "draft":
    case "awaiting_payment":
      return 0;
    case "paid":
    case "admin_review":
    case "needs_client_fix":
      return 1;
    case "assigned_to_owner":
    case "accepted_by_owner":
    case "rejected_by_owner":
      return 2;
    case "documents_preparing":
    case "documents_uploaded":
    case "documents_review":
    case "documents_revision":
      return 3;
    case "ready_for_client":
    case "completed":
      // Все шаги пройдены — длина, чтобы ни один не был «текущим».
      if (facts.registration_confirmed_at) return STEPS.length;
      return facts.ifns_receipt_uploaded_at ? 5 : 4;
    default:
      return null;
  }
}

export type StepState = "done" | "current" | "todo";

export function stepStates(status: ApplicationStatus | string, facts: TrackerFacts = {}): StepState[] | null {
  const step = currentStep(status, facts);
  if (step === null) return null;
  return STEPS.map((_, index) =>
    index < step ? "done" : index === step ? "current" : "todo"
  );
}

/** «2026-10-20» → «20.10.2026»; отметку времени (UTC) — датой по Москве. */
export function trackerDate(value: string): string {
  if (value.length <= 10) {
    const [y, m, d] = value.split("-");
    return d && m && y ? `${d}.${m}.${y}` : value;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" });
}

/** Сегодня по Москве в формате «YYYY-MM-DD» — для сравнения с датой из расписки. */
function todayMoscow(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Moscow" });
}

/**
 * Прогноз под полоской: строится от даты из расписки, а не от выдуманного срока.
 * `null` — прогнозировать нечего (документы ещё не выданы, расписки нет).
 */
export function trackerForecast(status: ApplicationStatus | string, facts: TrackerFacts = {}): string | null {
  if (!DOCUMENTS_ISSUED.has(status)) return null;
  if (facts.registration_confirmed_at) {
    return `Регистрация подтверждена ${trackerDate(facts.registration_confirmed_at)}`;
  }
  const expected = facts.registration_expected_on;
  if (!expected) return null;
  return expected <= todayMoscow()
    ? `Регистрация ожидалась ${trackerDate(expected)} — площадка сверяет данные с ЕГРЮЛ`
    : `Регистрация ожидается ${trackerDate(expected)}`;
}

/**
 * Короткий номер заявки для таблицы. Сквозной нумерации на бэкенде нет — есть
 * только UUID, поэтому берём его начало. Придумывать «A-2417» нельзя: такой
 * номер выглядит как настоящий, но в поддержке по нему ничего не найдут.
 *
 * Восемь символов — это 32 бита, и на нескольких тысячах заявок совпадение
 * перестаёт быть невероятным. В таблице этого хватает, чтобы различать строки
 * глазами, но полагаться на него как на идентификатор нельзя: везде, где номер
 * показан, рядом лежит полный id (атрибут title), и именно он идёт в поддержку.
 */
export function shortNumber(id: string): string {
  return id.replace(/-/g, "").slice(0, 8).toUpperCase();
}
