/**
 * Страница, куда Т-Банк возвращает покупателя с платёжной формы.
 *
 * Вошедшего на сайте сразу ведём в карточку заявки: там статус оплаты
 * проверяется у банка. Без сессии (форму открыли из мобильного приложения во
 * встроенной вкладке, или сессия истекла) — объясняем, что делать дальше.
 *
 * Страница ничего не засчитывает: «успех» в адресе — только слова банка о
 * том, что форма закрылась. Оплату подтверждает бэкенд по состоянию платежа
 * в Т-Банке.
 */
import { CheckCircle2, Clock3, LogIn, XCircle } from "lucide-react";
import { useEffect } from "react";
import type { PaymentReturnResult } from "../router";
import { markPaymentReturn } from "./paymentReturn";

export function PaymentReturnPage({
  result,
  applicationId,
  signedIn,
  onOpenApplication,
  onLogin,
}: {
  result: PaymentReturnResult;
  applicationId: string | null;
  signedIn: boolean;
  onOpenApplication: (applicationId: string | null) => void;
  onLogin: (applicationId: string | null) => void;
}) {
  const goStraightIn = signedIn;

  useEffect(() => {
    if (!goStraightIn) return;
    if (applicationId) markPaymentReturn(applicationId, result);
    onOpenApplication(applicationId);
  }, [goStraightIn, applicationId, result, onOpenApplication]);

  if (goStraightIn) {
    return (
      <main className="ds-verify">
        <div className="ds-verify__card">
          <Clock3 className="ds-verify__icon" size={38} />
          <h1>Возвращаем в личный кабинет…</h1>
        </div>
      </main>
    );
  }

  return (
    <main className="ds-verify">
      <div className="ds-verify__card">
        {result === "success" ? (
          <>
            <CheckCircle2 className="ds-verify__icon ds-verify__icon--ok" size={38} />
            <h1>Платёж отправлен</h1>
            <p>
              Как только банк подтвердит оплату, заявка перейдёт в статус «Оплачена» —
              обычно это занимает до пары минут.
            </p>
            <p className="ds-verify__hint">
              Если вы платили из приложения uradres, закройте эту страницу и вернитесь в
              него: статус заявки обновится сам.
            </p>
          </>
        ) : (
          <>
            <XCircle className="ds-verify__icon ds-verify__icon--err" size={38} />
            <h1>Оплата не завершена</h1>
            <p>
              Банк сообщил, что платёж не прошёл или был отменён. Попробовать ещё раз
              можно из карточки заявки. Если деньги всё же списались, статус заявки
              обновится сам.
            </p>
            <p className="ds-verify__hint">
              Если вы платили из приложения uradres, закройте эту страницу и вернитесь в
              него.
            </p>
          </>
        )}

        <button
          className="ds-btn ds-btn--primary ds-btn--md"
          onClick={() => {
            if (applicationId) markPaymentReturn(applicationId, result);
            onLogin(applicationId);
          }}
          type="button"
        >
          <LogIn size={15} /> Войти в личный кабинет
        </button>
      </div>
    </main>
  );
}
