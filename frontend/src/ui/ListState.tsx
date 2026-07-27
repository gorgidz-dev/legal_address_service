/**
 * Три состояния списка — загрузка, пусто, ошибка — одним набором на все разделы.
 *
 * Раньше каждый кабинет решал сам: скелет из пяти одинаковых полосок в одном
 * месте, «нет данных» текстом в другом, красная плашка без единственного
 * действия, которое обычно помогает («обновить»), в третьем.
 */
import { Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Скелет повторяет ритм строки списка (заголовок, подпись, мета), а не рисует
 * пять одинаковых прямоугольников: так подмена на реальные данные не дёргает
 * высоту блока.
 */
export function ListLoading({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-busy="true" className="cab-liststate">
      {Array.from({ length: rows }).map((_, index) => (
        <div className="cab-skeleton-row" key={index}>
          <span className="cab-skeleton-line" style={{ width: "38%" }} />
          <span className="cab-skeleton-line cab-skeleton-line--lg" style={{ width: "72%" }} />
          <span className="cab-skeleton-line" style={{ width: "54%" }} />
        </div>
      ))}
      <span className="sr-only">Загружаем данные</span>
    </div>
  );
}

export function ListEmpty({
  title,
  text,
  action
}: {
  title: string;
  text: string;
  /** Кнопка появляется только там, где человеку правда есть что нажать. */
  action?: { label: string; onClick: () => void; icon?: ReactNode };
}) {
  return (
    <div className="cab-empty">
      <strong className="cab-empty__title">{title}</strong>
      <span className="cab-empty__text">{text}</span>
      {action ? (
        <button className="cab-btn cab-btn--primary cab-btn--sm" onClick={action.onClick} type="button">
          {action.icon}
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

/**
 * Ошибка списка. «Войти заново» показывается отдельно от «Обновить»: истёкшая
 * сессия и упавший запрос лечатся по-разному, а раньше обе выглядели одинаково
 * — красной строкой без выхода.
 */
export function ListError({
  message,
  onRetry,
  onRelogin,
  busy = false
}: {
  message: string;
  onRetry?: () => void;
  onRelogin?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="cab-error" role="alert">
      <strong className="cab-error__title">Не удалось загрузить</strong>
      <span className="cab-error__text">{message}</span>
      {onRetry || onRelogin ? (
        <div className="cab-error__actions">
          {onRetry ? (
            <button className="cab-btn cab-btn--sm" disabled={busy} onClick={onRetry} type="button">
              {busy ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
              Обновить
            </button>
          ) : null}
          {onRelogin ? (
            <button className="cab-btn cab-btn--sm" onClick={onRelogin} type="button">
              Войти заново
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
