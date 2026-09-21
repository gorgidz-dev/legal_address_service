/**
 * Метка «покупатель только что вернулся с формы банка».
 *
 * Страница возврата (/payment/success|fail) переводит вошедшего пользователя в
 * карточку заявки, а карточке надо знать, что он пришёл из банка: тогда она
 * несколько минут ждёт подтверждения оплаты вместо того, чтобы снова
 * показывать «Оплатить». Кабинетный маршрут параметров не несёт, поэтому
 * метка лежит в sessionStorage — она живёт только в этой вкладке.
 *
 * Метка ничего не решает об оплате: статус приходит с бэкенда, который
 * сверяется с банком. Поэтому её подделка ничего не даёт.
 */
import type { PaymentReturnResult } from "../router";

const KEY = "uradres.paymentReturn";
/** Метка старше этого — просто забытая вкладка, ожидание не включаем. */
const MAX_AGE_MS = 30 * 60 * 1000;

type Mark = { applicationId: string; result: PaymentReturnResult; at: number };

export function markPaymentReturn(applicationId: string, result: PaymentReturnResult): void {
  try {
    const mark: Mark = { applicationId, result, at: Date.now() };
    window.sessionStorage.setItem(KEY, JSON.stringify(mark));
  } catch {
    // Приватный режим / запрет хранилища: карточка просто покажет текущий статус.
  }
}

/** Забрать метку для этой заявки (одноразово). */
export function takePaymentReturn(applicationId: string): PaymentReturnResult | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const mark = JSON.parse(raw) as Partial<Mark>;
    if (mark.applicationId !== applicationId) return null;
    window.sessionStorage.removeItem(KEY);
    if (typeof mark.at !== "number" || Date.now() - mark.at > MAX_AGE_MS) return null;
    return mark.result === "success" || mark.result === "fail" ? mark.result : null;
  } catch {
    return null;
  }
}
