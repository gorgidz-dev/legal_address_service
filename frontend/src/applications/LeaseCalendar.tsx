/**
 * Календарь аренды: ближайшие сроки по действующим договорам.
 *
 * Один компонент на оба кабинета. Отличается только подпись контрагента:
 * клиенту показываем собственника, собственнику — компанию клиента. Само
 * поле приходит с бэкенда уже подставленным, здесь только заголовок колонки.
 *
 * Это не сетка-календарь с клетками месяца: аренд у одной стороны единицы, и
 * список, отсортированный по дате окончания, отвечает на вопрос «что горит»
 * быстрее, чем поиск подсвеченной клетки в сетке.
 */
import { CalendarClock } from "lucide-react";
import type { LeaseCalendarItem, RenewalStatus } from "../types";
import { ListEmpty } from "../ui/ListState";

const STATUS_TONE: Record<RenewalStatus, string> = {
  overdue: "cab-lease__badge cab-lease__badge--overdue",
  due_soon: "cab-lease__badge cab-lease__badge--soon",
  active: "cab-lease__badge",
};

function statusText(item: LeaseCalendarItem): string {
  const days = item.days_until_renewal;
  if (days < 0) {
    const overdue = -days;
    return overdue === 1 ? "истёк вчера" : `истёк ${overdue} дн. назад`;
  }
  if (days === 0) return "истекает сегодня";
  if (days === 1) return "истекает завтра";
  return `через ${days} дн.`;
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parsed);
}

export function LeaseCalendar({
  items,
  counterpartyLabel,
}: {
  items: LeaseCalendarItem[];
  /** «Собственник» в кабинете клиента, «Клиент» — в кабинете собственника. */
  counterpartyLabel: string;
}) {
  if (items.length === 0) {
    return (
      <ListEmpty
        title="Действующих договоров нет"
        text="Здесь появятся сроки аренды, когда договор будет подписан."
      />
    );
  }

  return (
    <div className="cab-lease">
      {items.map((item) => (
        <article className="cab-lease__row" key={item.contract_id}>
          <span className="cab-lease__icon" aria-hidden="true">
            <CalendarClock size={18} strokeWidth={1.8} />
          </span>

          <div className="cab-lease__main">
            <h3 className="cab-lease__address">
              {item.address_full}
              {item.room_number ? `, ${item.room_number}` : ""}
            </h3>
            <p className="cab-lease__meta">
              {counterpartyLabel}: {item.counterparty} · договор {item.contract_number}
            </p>
          </div>

          <div className="cab-lease__dates">
            <span className="cab-lease__period">
              {formatDate(item.start_date)} — {formatDate(item.end_date)}
            </span>
            <span className={STATUS_TONE[item.renewal_status]}>{statusText(item)}</span>
          </div>
        </article>
      ))}
    </div>
  );
}
