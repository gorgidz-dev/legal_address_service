/**
 * Раздел «Цены и тарифы» — цель ссылки #pricing в верхнем меню.
 *
 * Тексты держатся ровно того, что есть в коде и оферте (решение владельца
 * 2026-07-28: ни сроков, ни процентов, ни «гарантий» без механики за ними):
 * - сумма = аренда за срок + корреспонденция × месяцев (app/services/application_pricing);
 * - дополнительные услуги адреса подключаются после заявки и в счёт не входят;
 * - продление — новая заявка на тот же адрес;
 * - возврат — оферта, раздел 5.
 *
 * Кому платит клиент, зависит от типа заявки (модель площадки, CLAUDE.md):
 * - первичная регистрация — вся сумма площадке (СБП), площадка рассчитывается
 *   с собственником после выдачи документов, удержав комиссию;
 * - смена адреса — счёт выставляет собственник (manual_invoice), комиссию
 *   площадке он платит сам.
 * В обоих случаях комиссия площадки уже внутри цены адреса, сверху не добавляется.
 *
 * Диапазон цен — из /marketplace/price-summary по всему каталогу, а не из
 * текущей выдачи: фильтры посетителя не должны менять «от и до» в тарифах.
 */
import {
  Building2,
  CalendarClock,
  FileCheck2,
  Mail,
  MessageSquare,
  Plus,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { LegalDoc } from "../router";
import type { CatalogPriceSummary, PriceRange } from "../types";

function rub(value: string): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Number(value));
}

/** «12 000 – 40 000 ₽» или «12 000 ₽», если в каталоге одна цена. */
function formatRange(range: PriceRange | null | undefined): string | null {
  if (!range) return null;
  return Number(range.min) === Number(range.max)
    ? `${rub(range.min)} ₽`
    : `${rub(range.min)} – ${rub(range.max)} ₽`;
}

const INCLUDED = [
  {
    icon: FileCheck2,
    title: "Комплект документов",
    text: "Гарантийное письмо, выписка ЕГРН и договор аренды — в личном кабинете, в DOCX и PDF.",
  },
  {
    icon: ShieldCheck,
    title: "Проверка комплекта",
    text: "Документы от собственника проверяет оператор площадки, прежде чем они попадут к вам.",
  },
  {
    icon: MessageSquare,
    title: "Поддержка",
    text: "Переписка с собственником и площадкой в кабинете — с файлами и историей по адресу.",
  },
];

export function HomePricing({ onOpenLegal }: { onOpenLegal: (doc: LegalDoc) => void }) {
  const [summary, setSummary] = useState<CatalogPriceSummary | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .publicPriceSummary()
      .then((result) => alive && setSummary(result))
      // Без диапазона раздел остаётся полезным: цены есть в карточках.
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const range6 = formatRange(summary?.price_6m);
  const range11 = formatRange(summary?.price_11m);
  const rangeCorr = formatRange(summary?.correspondence);

  return (
    <section className="ds-pricing" id="pricing" aria-label="Цены и тарифы">
      <div className="ds-pricing__inner">
        <div className="ds-pricing__intro">
          <span className="ds-pricing__eyebrow">Цены и тарифы</span>
          <h2 className="ds-pricing__title">Одна сумма за весь срок аренды</h2>
          <p className="ds-pricing__sub">
            Цену адреса задаёт собственник, она указана в карточке. Комиссия площадки уже
            входит в неё — сверху ничего не добавляется.
          </p>
        </div>

        <div className="ds-pricing__terms">
          {[
            { months: 6, range: range6 },
            { months: 11, range: range11 },
          ].map((term) => (
            <div className="ds-pricing__term" key={term.months}>
              <span className="ds-pricing__term-label">Адрес на {term.months} месяцев</span>
              <strong className="ds-pricing__term-price">{term.range ?? "Цена в карточке адреса"}</strong>
              <span className="ds-pricing__term-note">
                {term.range ? "за весь срок, по адресам каталога" : "зависит от адреса"}
              </span>
            </div>
          ))}
        </div>

        <div className="ds-pricing__formula" aria-label="Из чего складывается сумма">
          <span className="ds-pricing__formula-part">
            <b>Цена адреса</b>
            <small>за 6 или 11 месяцев</small>
          </span>
          <span className="ds-pricing__formula-op" aria-hidden="true">+</span>
          <span className="ds-pricing__formula-part">
            <b>Приём почты</b>
            <small>по желанию, × месяцев срока</small>
          </span>
          <span className="ds-pricing__formula-op" aria-hidden="true">=</span>
          <span className="ds-pricing__formula-part ds-pricing__formula-part--total">
            <b>Сумма к оплате</b>
            <small>один платёж за весь срок</small>
          </span>
        </div>

        <div className="ds-pricing__columns">
          <div className="ds-pricing__block">
            <h3>Что входит в цену</h3>
            <ul className="ds-pricing__list">
              {INCLUDED.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.title}>
                    <span className="ds-pricing__icon" aria-hidden="true">
                      <Icon size={18} strokeWidth={1.8} />
                    </span>
                    <span>
                      <b>{item.title}</b>
                      {item.text}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="ds-pricing__block">
            <h3>Что оплачивается отдельно</h3>
            <ul className="ds-pricing__list">
              <li>
                <span className="ds-pricing__icon" aria-hidden="true">
                  <Mail size={18} strokeWidth={1.8} />
                </span>
                <span>
                  <b>Приём корреспонденции</b>
                  Если адрес её предлагает{rangeCorr ? `: ${rangeCorr} в месяц` : ""}. Оплачивается
                  сразу за весь срок и входит в ту же сумму.
                </span>
              </li>
              <li>
                <span className="ds-pricing__icon" aria-hidden="true">
                  <Plus size={18} strokeWidth={1.8} />
                </span>
                <span>
                  <b>Дополнительные услуги адреса</b>
                  Перечислены в карточке. Подключаются после оформления заявки и в сумму к оплате
                  не входят.
                </span>
              </li>
              <li>
                <span className="ds-pricing__icon" aria-hidden="true">
                  <CalendarClock size={18} strokeWidth={1.8} />
                </span>
                <span>
                  <b>Продление</b>
                  Срок договора виден в личном кабинете. Продлить — новой заявкой на тот же адрес
                  по цене каталога на момент продления.
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div className="ds-pricing__block">
          <h3>Кому и как платить</h3>
          <ul className="ds-pricing__list ds-pricing__list--split">
            <li>
              <span className="ds-pricing__icon" aria-hidden="true">
                <Smartphone size={18} strokeWidth={1.8} />
              </span>
              <span>
                <b>Регистрация новой компании</b>
                Оплачиваете площадке через СБП после того, как собственник подтвердил заявку.
                С собственником площадка рассчитывается сама, после выдачи вам документов.
              </span>
            </li>
            <li>
              <span className="ds-pricing__icon" aria-hidden="true">
                <Building2 size={18} strokeWidth={1.8} />
              </span>
              <span>
                <b>Смена адреса действующей компании</b>
                Счёт выставляет собственник — он появится в личном кабинете. Оплачиваете его с
                расчётного счёта компании и прикладываете платёжное поручение там же.
              </span>
            </li>
          </ul>
        </div>

        <p className="ds-pricing__footnote">
          Когда возвращаются деньги — в{" "}
          <button className="ds-about__link" onClick={() => onOpenLegal("offer")} type="button">
            публичной оферте
          </button>
          , раздел 5.
        </p>
      </div>
    </section>
  );
}
