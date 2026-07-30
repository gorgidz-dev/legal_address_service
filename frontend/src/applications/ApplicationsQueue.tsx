/**
 * Очередь заявок: одна таблица на все кабинеты.
 *
 * Раньше одна и та же сущность выглядела по-разному в четырёх местах —
 * .client-application, .owner-application, .simple-item и строка реестра.
 *
 * Колонка срока появилась вместе с полем applications.sla_due_at (30.07.2026).
 * До него дедлайна не было ни в модели, ни в схемах, и вместо выдуманного
 * «просрочено 6 ч» здесь стояло честное «обновлена». Теперь срок настоящий —
 * но только там, где он есть: у клиента дедлайнов нет по решению владельца,
 * поэтому колонка переключается пропом `showSla`, а не гадает по данным.
 */
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { statusMeta } from "../status";
import { StatusBadge } from "../ui/Badge";
import { ListEmpty } from "../ui/ListState";
import { shortNumber } from "./progress";

export type QueueRow = {
  id: string;
  /** Компания или клиент — то, по чему заявку узнают. */
  subject: string;
  address: string;
  status: string;
  /** ISO-дата последнего изменения. */
  updatedAt: string | null;
  /** Внутренний срок этапа. null — в этом статусе ждать нечего. */
  slaDueAt?: string | null;
  amount: string;
};

export type QueueFilter = {
  id: string;
  label: string;
  match: (row: QueueRow) => boolean;
};

function relativeDate(value: string | null): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return "сегодня";
  if (days === 1) return "вчера";
  if (days < 7) return `${days} дн. назад`;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit" }).format(then);
}

/**
 * Срок этапа словами. Возвращает и текст, и признак просрочки — подсветку
 * строки решает вызывающий, чтобы не дублировать здесь разбор даты.
 */
function slaState(value: string | null | undefined): { text: string; overdue: boolean } {
  if (!value) return { text: "—", overdue: false };
  const due = new Date(value).getTime();
  if (Number.isNaN(due)) return { text: "—", overdue: false };

  const msLeft = due - Date.now();
  const dayMs = 86_400_000;
  if (msLeft < 0) {
    const days = Math.floor(-msLeft / dayMs);
    if (days === 0) return { text: "просрочено сегодня", overdue: true };
    if (days === 1) return { text: "просрочено на день", overdue: true };
    return { text: `просрочено на ${days} дн.`, overdue: true };
  }
  const days = Math.floor(msLeft / dayMs);
  if (days === 0) return { text: "сегодня", overdue: false };
  if (days === 1) return { text: "завтра", overdue: false };
  return { text: `через ${days} дн.`, overdue: false };
}

/** Экспорт выборки. Полностью на клиенте — эндпоинта выгрузки нет. */
function exportCsv(rows: QueueRow[]): void {
  const header = ["Номер", "Субъект", "Адрес", "Статус", "Обновлена", "Срок", "Сумма"];
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const body = rows.map((row) =>
    [
      shortNumber(row.id),
      row.subject,
      row.address,
      statusMeta(row.status).label,
      row.updatedAt ? new Date(row.updatedAt).toLocaleString("ru-RU") : "",
      row.slaDueAt ? new Date(row.slaDueAt).toLocaleString("ru-RU") : "",
      row.amount,
    ]
      .map(escape)
      .join(";")
  );
  // BOM — иначе Excel открывает кириллицу как «ÐÐ°ÑÐ²Ð°Ð½Ð¸Ðµ».
  const blob = new Blob(["﻿" + [header.map(escape).join(";"), ...body].join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "zayavki.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function ApplicationsQueue({
  rows,
  selectedId,
  onSelect,
  filters,
  subjectLabel = "Компания",
  showSla = false,
  drawer,
}: {
  rows: QueueRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Наборы фильтров различаются по ролям — приходят снаружи. */
  filters: QueueFilter[];
  subjectLabel?: string;
  /** Показывать колонку срока. У клиента дедлайнов нет — колонка остаётся «Обновлена». */
  showSla?: boolean;
  drawer: React.ReactNode;
}) {
  const [filterId, setFilterId] = useState<string>(filters[0]?.id || "all");
  const [checked, setChecked] = useState<string[]>([]);

  const activeFilter = filters.find((item) => item.id === filterId) || filters[0];
  const visible = useMemo(
    () => (activeFilter ? rows.filter(activeFilter.match) : rows),
    [rows, activeFilter]
  );
  /** Фильтр «показать всё» — на него уводит кнопка из пустого состояния. */
  const showAllId = (filters.find((item) => item.id === "all") || filters[0])?.id;

  const checkedRows = useMemo(
    () => visible.filter((row) => checked.includes(row.id)),
    [visible, checked]
  );
  const allChecked = visible.length > 0 && checkedRows.length === visible.length;

  function toggle(id: string) {
    setChecked((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {filters.length > 1 ? (
        <div className="cab-toolbar">
          <span className="cab-toolbar__label">Фильтры</span>
          {filters.map((filter) => (
            <button
              aria-pressed={filter.id === filterId}
              className={filter.id === filterId ? "cab-chip is-active" : "cab-chip"}
              key={filter.id}
              onClick={() => setFilterId(filter.id)}
              type="button"
            >
              {filter.label}
            </button>
          ))}
          <span className="cab-toolbar__spacer" />
          <button className="cab-btn cab-btn--sm" onClick={() => exportCsv(visible)} type="button">
            <Download size={14} /> Экспорт
          </button>
        </div>
      ) : null}

      {/*
        Массовых действий из макета («Назначить собственнику», «Вернуть на
        доработку» для выборки) здесь нет: bulk-эндпоинта не существует, а цикл
        поштучных вызовов — это N транзакций, часть которых упадёт с 409 на
        несовпадении статуса. Обещать атомарность, которой нет, хуже, чем не
        обещать ничего. Выбор строк оставлен ради выгрузки.
      */}
      {checkedRows.length > 0 ? (
        <div className="cab-bulkbar">
          <strong style={{ fontSize: 13 }}>Выбрано заявок: {checkedRows.length}</strong>
          <span className="cab-toolbar__spacer" />
          <button className="cab-btn cab-btn--sm" onClick={() => exportCsv(checkedRows)} type="button">
            <Download size={14} /> Выгрузить выбранные
          </button>
          <button className="cab-btn cab-btn--sm" onClick={() => setChecked([])} type="button">
            Снять выбор
          </button>
        </div>
      ) : null}

      <div className="cab-queue">
        <div className="cab-table">
          <div className="cab-table__head">
            <span>
              <input
                aria-label="Выбрать все заявки"
                checked={allChecked}
                onChange={() => setChecked(allChecked ? [] : visible.map((row) => row.id))}
                style={{ accentColor: "var(--ds-indigo-600)" }}
                type="checkbox"
              />
            </span>
            <span>Номер</span>
            <span>{subjectLabel}</span>
            <span>Адрес</span>
            <span>Статус</span>
            <span>{showSla ? "Срок" : "Обновлена"}</span>
            <span style={{ textAlign: "right" }}>Сумма</span>
          </div>

          {/*
            Фильтр может не совпасть ни с одной строкой — и у собственника это
            состояние по умолчанию: «Требуют действия» стоит первым, а если
            срочного нет, кабинет открывался пустой таблицей без объяснений.
            Заявки при этом есть, просто их не видно.
          */}
          {visible.length === 0 ? (
            <div style={{ padding: "18px 16px" }}>
              <ListEmpty
                action={
                  filters.length > 1
                    ? { label: "Показать все", onClick: () => setFilterId(showAllId) }
                    : undefined
                }
                text={
                  rows.length
                    ? `Под фильтр «${activeFilter?.label}» не попала ни одна из ${rows.length} заявок.`
                    : "Заявок пока нет."
                }
                title="Ничего не найдено"
              />
            </div>
          ) : null}

          {visible.map((row) => (
            <div
              className={row.id === selectedId ? "cab-table__row is-selected" : "cab-table__row"}
              key={row.id}
              onClick={() => onSelect(row.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(row.id);
                }
              }}
            >
              <span onClick={(event) => event.stopPropagation()}>
                <input
                  aria-label={`Выбрать заявку ${shortNumber(row.id)}`}
                  checked={checked.includes(row.id)}
                  onChange={() => toggle(row.id)}
                  style={{ accentColor: "var(--ds-indigo-600)" }}
                  type="checkbox"
                />
              </span>
              <span className="cab-table__id" title={row.id}>
                {shortNumber(row.id)}
              </span>
              <span className="cab-table__cell--ellipsis" style={{ fontSize: 13, fontWeight: 600 }}>
                {row.subject}
              </span>
              <span
                className="cab-table__cell--ellipsis"
                style={{ fontSize: 12.5, color: "var(--ds-slate-500)" }}
                title={row.address}
              >
                {row.address}
              </span>
              <StatusBadge short status={row.status} />
              {showSla ? (
                (() => {
                  const sla = slaState(row.slaDueAt);
                  return (
                    <span
                      className={sla.overdue ? "cab-sla cab-sla--overdue" : "cab-sla"}
                      title={row.slaDueAt ? new Date(row.slaDueAt).toLocaleString("ru-RU") : undefined}
                    >
                      {sla.text}
                    </span>
                  );
                })()
              ) : (
                <span className="cab-sla">{relativeDate(row.updatedAt)}</span>
              )}
              <b className="cab-table__amount">{row.amount}</b>
            </div>
          ))}

          <div className="cab-table__foot">
            <span>
              {visible.length === rows.length
                ? `Заявок: ${rows.length}`
                : `Показано ${visible.length} из ${rows.length}`}
            </span>
          </div>
        </div>

        {drawer}
      </div>
    </div>
  );
}
