/**
 * Кнопка оплаты в фирменном стиле СБП.
 *
 * Оформление — по «Рекомендациям по дизайну элементов и брендированию экранов
 * оплаты» НСПК (sbp.nspk.ru/banks → «Руководство для e-commerce»):
 * - фон #1d1346 на светлой странице (#f5f1e8 — только для тёмной темы, у
 *   кабинета её нет);
 * - вариант с call-to-action «Оплатить» + знак СБП: из карточки заявки не
 *   очевидно, что кнопка именно платёжная;
 * - высота как у остальных кнопок страницы (min-height .btn — 38px);
 * - логотип официальный: знак + «сбп» с белой надписью, векторы взяты из
 *   архива НСПК logo.zip (sbp_logo_rgb.pdf, артборд 7) без изменений.
 */
import { Loader2 } from "lucide-react";
import sbpLogoOnDark from "./sbp-logo-on-dark.svg";

export function SbpPayButton({
  onClick,
  busy = false,
  disabled = false,
}: {
  onClick: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      aria-busy={busy}
      aria-label="Оплатить через СБП"
      className="sbp-pay-btn"
      disabled={disabled || busy}
      onClick={onClick}
      type="button"
    >
      {busy ? <Loader2 aria-hidden="true" className="spin" size={16} /> : null}
      <span className="sbp-pay-btn__cta">Оплатить</span>
      <img alt="" aria-hidden="true" className="sbp-pay-btn__logo" src={sbpLogoOnDark} />
    </button>
  );
}
