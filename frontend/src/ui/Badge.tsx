/**
 * Бейдж состояния — один на всё приложение.
 *
 * Заменяет две несогласованные системы: `.status.<status>` (правила были
 * разложены по двум CSS-файлам и противоречили друг другу) и `.ds-badge--*`
 * (пять модификаторов, из которых в разметке жил один).
 */
import type { ReactNode } from "react";
import { statusMeta, type Tone } from "../status";

export function Badge({
  tone = "neutral",
  title,
  children
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span className={`cab-badge cab-badge--${tone}`} title={title}>
      {children}
    </span>
  );
}

/**
 * Бейдж статуса заявки. `short` — для ячейки таблицы, где места на полную
 * подпись нет; полная при этом остаётся в подсказке, чтобы «У собственника»
 * не пришлось расшифровывать по памяти.
 */
export function StatusBadge({
  status,
  short = false
}: {
  status: string | null | undefined;
  short?: boolean;
}) {
  const meta = statusMeta(status);
  return (
    <Badge title={short ? meta.label : undefined} tone={meta.tone}>
      {short ? meta.short : meta.label}
    </Badge>
  );
}
