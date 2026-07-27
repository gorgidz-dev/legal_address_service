/**
 * Панель заявки: шапка, прогресс, вкладки «Заявка · Документы · Чат».
 *
 * Собирает в одном месте то, что раньше было разнесено: детали заявки лежали в
 * одной колонке, документы — ниже отдельным блоком, а переписка вообще в другом
 * разделе. Лента событий появилась у собственника наравне с клиентом.
 *
 * Содержимое вкладок приходит снаружи: у ролей разные права и разные действия,
 * и зашивать их сюда значило бы снова описывать поведение трижды.
 */
import { useEffect, useState, type ReactNode } from "react";
import { statusMeta } from "../status";
import { StatusBadge } from "../ui/Badge";
import { shortNumber, STEPS, stepStates } from "./progress";

export type DrawerTab = "main" | "docs" | "chat";

export function ApplicationDrawer({
  id,
  title,
  address,
  status,
  docsCount,
  docsDisabledReason,
  chatDisabledReason,
  main,
  docs,
  chat,
}: {
  id: string;
  title: string;
  address: string;
  status: string;
  /** `null` — ещё не считали (счётчик не показываем, а не рисуем ноль). */
  docsCount: number | null;
  /** Если задано — вкладка недоступна, текст объясняет почему. */
  docsDisabledReason?: string | null;
  chatDisabledReason?: string | null;
  main: ReactNode;
  docs: ReactNode;
  chat: ReactNode;
}) {
  const [tab, setTab] = useState<DrawerTab>("main");

  // Смена заявки сбрасывает вкладку: иначе, переключившись на «Документы» у
  // одной заявки, человек видел бы вкладку документов у следующей и решил, что
  // это её файлы.
  useEffect(() => {
    setTab("main");
  }, [id]);

  const states = stepStates(status);

  return (
    <aside className="cab-drawer">
      <div className="cab-drawer__head">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          {/* Короткий номер для глаз, полный id — для поддержки: он в title и
              выделяется мышью целиком при копировании строки. */}
          <span className="cab-drawer__id" title={id}>
            {shortNumber(id)}
          </span>
          <StatusBadge status={status} />
        </div>
        <h2 className="cab-drawer__title">{title}</h2>
        <span className="cab-drawer__address">{address}</span>

        {states ? (
          <div className="cab-steps">
            {STEPS.map((label, index) => (
              <div
                className={
                  states[index] === "done"
                    ? "cab-step is-done"
                    : states[index] === "current"
                      ? "cab-step is-current"
                      : "cab-step"
                }
                key={label}
              >
                <span className="cab-step__bar" />
                <span className="cab-step__label">{label}</span>
              </div>
            ))}
          </div>
        ) : (
          // Отменённые, спорные и старые договорные заявки вне цепочки: полоска
          // показывала бы движение вперёд там, где его нет.
          <span className="cab-drawer__address">{statusMeta(status).label}</span>
        )}
      </div>

      <div className="cab-tabs" role="tablist">
        <TabButton active={tab === "main"} label="Заявка" onClick={() => setTab("main")} />
        <TabButton
          active={tab === "docs"}
          count={docsCount}
          disabledReason={docsDisabledReason}
          label="Документы"
          onClick={() => setTab("docs")}
        />
        <TabButton
          active={tab === "chat"}
          disabledReason={chatDisabledReason}
          label="Чат"
          onClick={() => setTab("chat")}
        />
      </div>

      <div className="cab-drawer__body">
        {tab === "main" ? main : tab === "docs" ? docs : chat}
      </div>
    </aside>
  );
}

function TabButton({
  label,
  active,
  onClick,
  count,
  disabledReason,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number | null;
  disabledReason?: string | null;
}) {
  return (
    <button
      aria-selected={active}
      className={active ? "cab-tab is-active" : "cab-tab"}
      disabled={Boolean(disabledReason)}
      onClick={onClick}
      role="tab"
      title={disabledReason || undefined}
      type="button"
    >
      {label}
      {typeof count === "number" && count > 0 ? (
        <span className="cab-tab__count">{count}</span>
      ) : null}
    </button>
  );
}

/** Пара «ключ — значение» в панели. */
export function DrawerRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="cab-kv__row">
      <span className="cab-kv__label">{label}</span>
      <span className="cab-kv__value">{value}</span>
    </div>
  );
}

/** Лента событий заявки. */
export function DrawerTimeline({
  events,
  emptyText,
}: {
  events: Array<{ id: string; title: string; message: string; created_at: string }>;
  emptyText: string;
}) {
  if (!events.length) {
    return (
      <div className="cab-timeline">
        <div className="cab-timeline__head">История</div>
        <p className="cab-timeline__text">{emptyText}</p>
      </div>
    );
  }
  return (
    <div className="cab-timeline">
      <div className="cab-timeline__head">
        История
        <span className="cab-timeline__meta">событий: {events.length}</span>
      </div>
      {events.map((event, index) => (
        <div className="cab-timeline__item" key={event.id}>
          <div className="cab-timeline__rail">
            <span className="cab-timeline__dot cab-timeline__dot--brand" />
            {index < events.length - 1 ? <span className="cab-timeline__line" /> : null}
          </div>
          <div className="cab-timeline__body">
            <span className="cab-timeline__title">{event.title}</span>
            <span className="cab-timeline__date">
              {new Intl.DateTimeFormat("ru-RU", {
                day: "2-digit",
                month: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              }).format(new Date(event.created_at))}
            </span>
            {event.message ? <p className="cab-timeline__text">{event.message}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
