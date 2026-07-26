/**
 * Подтверждение e-mail: страница по ссылке из письма и напоминание в кабинете.
 *
 * Публичная форма заявки заводит аккаунт на любой введённый адрес. Опечатка —
 * человек теряет доступ и не получает уведомлений; чужой адрес — занимает
 * учётку его владельца.
 *
 * Вход намеренно не блокируется: заявка и аккаунт создаются одним действием, и
 * запертый сразу после отправки клиент означал бы потерянную заявку.
 */
import { CheckCircle2, Home, Loader2, MailWarning, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";

type State =
  | { kind: "loading" }
  | { kind: "ok"; message: string }
  | { kind: "error"; message: string };

export function EmailVerificationPage({
  token,
  onHome,
}: {
  token: string;
  onHome: () => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    api
      .confirmEmailVerification(token)
      .then((result) => {
        if (alive) setState({ kind: "ok", message: result.message });
      })
      .catch((err: Error) => {
        if (!alive) return;
        const message =
          err instanceof ApiError ? err.message : "Не удалось подтвердить адрес";
        setState({ kind: "error", message });
      });
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <main className="ds-verify">
      <div className="ds-verify__card">
        {state.kind === "loading" ? (
          <>
            <Loader2 className="spin" size={30} />
            <h1>Подтверждаем адрес…</h1>
          </>
        ) : state.kind === "ok" ? (
          <>
            <CheckCircle2 className="ds-verify__icon ds-verify__icon--ok" size={38} />
            <h1>{state.message}</h1>
            <p>Теперь уведомления по заявкам будут приходить на вашу почту.</p>
          </>
        ) : (
          <>
            <XCircle className="ds-verify__icon ds-verify__icon--err" size={38} />
            <h1>Не получилось</h1>
            <p>{state.message}</p>
            <p className="ds-verify__hint">
              Новую ссылку можно запросить в личном кабинете — там же, где висит
              напоминание о неподтверждённом адресе.
            </p>
          </>
        )}

        <button className="ds-btn ds-btn--primary ds-btn--md" onClick={onHome} type="button">
          <Home size={15} /> На главную
        </button>
      </div>
    </main>
  );
}

/** Полоса-напоминание в кабинете, пока адрес не подтверждён. */
export function EmailVerificationBanner({ email }: { email: string }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    setBusy(true);
    setNote(null);
    setError(null);
    try {
      const result = await api.requestEmailVerification();
      setNote(result.message);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="email-verify-banner">
      <MailWarning size={18} />
      <div className="email-verify-banner__text">
        <strong>Подтвердите e-mail</strong>
        {/* Не утверждаем, что письмо уже отправлено: отправка может быть не
            настроена, и человек ждал бы письмо напрасно. Результат сообщает
            сервер по нажатию кнопки. */}
        <span>
          Адрес {email} не подтверждён. Без подтверждения мы не сможем прислать
          уведомления по заявке и восстановить доступ.
        </span>
        {note ? <span className="email-verify-banner__note">{note}</span> : null}
        {error ? <span className="email-verify-banner__error">{error}</span> : null}
      </div>
      <button className="text-action" disabled={busy} onClick={resend} type="button">
        {busy ? <Loader2 className="spin" size={15} /> : null}
        Отправить ссылку
      </button>
    </div>
  );
}
