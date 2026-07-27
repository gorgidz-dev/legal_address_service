/**
 * Прогресс заявки пятью шагами: Оплата → Проверка → Собственник → Документы →
 * Готово.
 *
 * Нужен, чтобы не заставлять читать ленту событий ради ответа на вопрос «где
 * сейчас моя заявка». Считается из статуса — отдельного поля этапа на бэкенде
 * нет, и заводить его ради полоски незачем: соответствие однозначное.
 */
import type { ApplicationStatus } from "../types";

export const STEPS = ["Оплата", "Проверка", "Собственник", "Документы", "Готово"] as const;

/**
 * Шаг, на котором заявка стоит сейчас. `null` — заявка вне основной цепочки:
 * отменена, в споре, на возврате или это старый договорной поток. Рисовать для
 * них полоску нельзя — она показывала бы движение вперёд там, где его нет.
 */
export function currentStep(status: ApplicationStatus | string): number | null {
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
      return 4;
    case "completed":
      // Все шаги пройдены: возвращаем длину, чтобы ни один не был «текущим».
      return STEPS.length;
    default:
      return null;
  }
}

export type StepState = "done" | "current" | "todo";

export function stepStates(status: ApplicationStatus | string): StepState[] | null {
  const step = currentStep(status);
  if (step === null) return null;
  return STEPS.map((_, index) =>
    index < step ? "done" : index === step ? "current" : "todo"
  );
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
